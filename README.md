# Jupiter

**See which files your teammates' Claude Code instances are touching — before your agent
overwrites their work.**

When several developers point Claude Code at the same repo, their agents silently clobber each
other. Jupiter gives every instance a shared view: Claude declares what it is about to edit, sees
who else already holds that file, and gets an instant warning on a collision.

Claims are **advisory** and **auto-expire**. Nothing is ever blocked, and a crashed agent can
never wedge the team.

```
Claude Code (teammate)  ──HTTP MCP──┐
Browser dashboard       ──SSE+fetch─┤
                                    ▼
                         FastAPI + AgentFlow
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
          Neon Postgres    Coordination Advisor   MCP server
                            (AgentFlow agent)    (5 tools, bearer auth)
```

## What the agent does

The deterministic rule catches two people on the *same* path. The **coordination advisor** — an
AgentFlow agent — catches the other half: two people on **different** files whose work collides
anyway.

```
Claims:
  Alice  src/auth/session.ts          (adding refresh-token rotation)
  Bob    tests/auth/session.test.ts   (covering token expiry)
  Bob    docs/changelog.md

Possibly-related work on *different* files (advisory, AI-suggested):
  - src/auth/session.ts + tests/auth/session.test.ts (Alice, Bob, high confidence)
    - Alice is editing the session implementation while Bob edits its test file, so
      test changes will likely collide with the refresh-token rotation work.
```

Note what it *didn't* say: `docs/changelog.md` is also claimed, sits in the same repo, and was
correctly left alone. Precision matters far more than recall — an empty result is the expected
answer most of the time.

Three properties are load-bearing:

- **Additive.** Hard conflicts stay authoritative. An overlap can never change a claim's
  `clear`/`blocked` status, and never suppresses or re-ranks a real conflict.
- **Cheap.** The agent runs only when the *set* of active claims actually changes. The cache key
  excludes timestamps, so a TTL refresh doesn't invalidate a good answer, and a claim set with
  fewer than two files or two people short-circuits without a call.
- **Distrustful.** Nothing the agent says is believed. It may only point at paths that really are
  claimed; holders are read from our own data, never from its reply. Invented paths, wrong
  holders, groups that are really one person's own work, and findings with no reason are all
  dropped rather than rendered.

**Only paths, intents, holder names and short notes reach the model — never file contents, and
never stored snippets, even when snippet storage is switched on.** Leave `JUPITER_LLM_API_KEY`
unset and the feature switches itself off cleanly — `/api/semantic` reports `disabled` with a
reason and the dashboard card stays hidden.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in DATABASE_URL and MODEL_IQ_API_KEY

python -m jupiter_admin db-push                                    # create the six tables
python -m jupiter_admin create-org --name "My Team" --slug my-team # prints an admin key, once
python -m jupiter_admin join --slug my-team --display-name jupiter-advisor
#   -> prints a member key (jpm_...). Put it in .env as JUPITER_AGENT_API_KEY.

python app.py               # http://localhost:8000
```

Open the dashboard, walk the setup wizard, and it hands each teammate the one command they run:

```bash
claude mcp add --transport http jupiter --scope user \
  https://<your-host>/api/mcp \
  --header "Authorization: Bearer jpm_7_…"
```

## The five MCP tools

Claude gets these automatically once the MCP server is connected.

| Tool | What it does |
|---|---|
| `jupiter_checkin(working_dir?)` | Registers the session and returns a snapshot of the team |
| `jupiter_lock_file(file_path, intent = "editing", note?, line_start?, line_end?)` | Declares intent on a file, or a range of lines in it; returns `clear` or names who is in the way |
| `jupiter_unlock_file(file_path)` | Releases the claim |
| `jupiter_who_is_working()` | Every claim across the team, who holds it, when it expires |
| `jupiter_announce(message)` | Broadcasts a short status message |

`intent: "editing"` conflicts with any other claim; `intent: "reading"` only conflicts with
editors — two readers coexist happily.

### How a conflict is decided

A claim conflicts when **a different member** holds the **same normalised path**, **at least one
side is editing**, and **the claimed line ranges overlap**. Four consequences worth knowing:

- Your own second Claude Code instance never blocks your first — the rule compares people, not
  sessions.
- `src\payments.ts`, `src//payments.ts` and `src/../src/payments.ts` are all the same file.
- **A blocked claim is still recorded.** That is what makes this advisory: Jupiter reports the
  situation and the humans decide. It never refuses anything.
- Two people editing far-apart regions of one file don't block each other.

### Line ranges

`line_start`/`line_end` are optional. Omit them and you claim the **whole file** — which is what
every claim was before ranges existed, so old clients and old rows keep their original meaning,
and a whole-file claim still conflicts with every range on that path.

```
Alice  src/payments.ts:1-50      (editing)   ─┐ both clear: the ranges
Bob    src/payments.ts:400-450   (editing)   ─┘ don't touch

Bob    src/payments.ts:40-80     (editing)   →  ⚠ blocked by Alice (editing:1-50)
                                                 on src/payments.ts:40-80
```

Re-claiming to refresh a TTL without naming a range **keeps** the range you already hold — a
heartbeat must never silently widen a narrow claim to the whole file.

### Seeing the conflicting code (opt-in, off by default)

Set `JUPITER_STORE_SNIPPETS=true` and `jupiter_lock_file` will also accept a `code` argument: the
source of the lines you claimed. A teammate who hits a conflict can then see what you're actually
changing, in the dashboard's conflict modal.

This is off by default and deliberately so. Joining a team is open and keys cannot be revoked (see
*What this does not do*), so storing source raises the stakes of a leaked slug from "they see your
filenames" to "they read your code". Snippets live in their own table, are fetched only by an
explicit request for one claim (never in the activity payload or the SSE stream), and are **never
sent to any model**.

### Expiry

A claim lives `JUPITER_LOCK_TTL` seconds (default 300, floor 5) measured from the last time it was
**refreshed** — not from when it was first taken. A claim also dies with its session, even well
inside the TTL.

Nothing sweeps on a timer. Expiry happens lazily, as two `UPDATE … WHERE` statements folded into
the same transaction as whatever read or write triggered them. A clause that matches nothing
writes nothing.

Expiry is an `UPDATE`, never a `DELETE`. A lapsed claim keeps its row and gains a `released_at`
stamp, so the record of a conflict outlives the conflict.

### History

`/api/activity` answers "what is claimed **right now**", and every one of its reads filters
`released_at IS NULL`. That is correct for a dashboard and useless for a log — a claim vanishes
the moment it lapses, taking the evidence of any collision with it.

`GET /api/history?limit=N` is the same rows without that filter, newest first, so the dashboard's
**Log** page keeps showing a conflict after both claims behind it are gone. Each claim carries a
`state`:

| `state` | Meaning |
|---|---|
| `active` | Still held — `released_at` is null |
| `expired` | The sweep closed it; it had gone a full TTL unrefreshed |
| `released` | Closed sooner than the TTL — an explicit `jupiter_unlock_file`, or its session ended |

`state` is **inferred, not stored**. The sweep and an explicit unlock do the same thing to a row
— stamp `released_at` — so the only signal separating them is how long the claim had gone
unrefreshed when it closed. Treat it as a label, not a fact of record. The one case it reads
wrong: a claim whose session ended reports `released` however recently it was refreshed.

The dashboard re-fetches history when the set of live claims changes rather than on a timer,
since a claim entering or leaving `/api/activity` is exactly when history gains a row.

## API

**Public** — `GET /api/healthz` · `POST /api/orgs` · `POST /api/orgs/{slug}/join`

**Member or admin** — `GET /api/orgs/{slug}/members` · `GET /api/orgs/{slug}/activity` ·
`GET /api/activity` · `GET /api/history?limit=N` · `GET /api/announcements?limit=N` ·
`GET /api/orgs/{slug}/stream` *(SSE)* · `GET /api/semantic`

**Member only** — `POST /api/sessions` · `POST /api/sessions/{id}/heartbeat` ·
`DELETE /api/sessions/{id}` · `POST /api/locks` · `POST /api/locks/release` ·
`POST /api/announcements` · `GET /api/locks/{lock_id}/snippet`

**MCP** — `POST /api/mcp` · `POST /api/mcp/{key}`

Keys are accepted as `Authorization: Bearer <key>`, as a bare `Authorization: <key>` with no
scheme, or as `X-API-Key: <key>` — which wins if both are present.

Status codes: `401` bad or absent key · `403` wrong key kind or wrong org · `404` unknown org, or
**someone else's session** (deliberately not a 403, so the API never confirms a session id exists
to a caller who does not own it) · `409` duplicate slug or display name, or an already-ended
session · `422` empty path, bad intent, or an underivable slug.

## CLI

```bash
python -m jupiter_admin db-push
python -m jupiter_admin create-org --name "My Team" [--slug my-team]
python -m jupiter_admin join --slug my-team --display-name alice
python -m jupiter_admin list-members --slug my-team
python -m jupiter_admin semantic-status --slug my-team   # actually calls the model
python -m jupiter_admin whoami --key jpm_...
```

## Configuration

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `DATABASE_URL` | yes | — | Postgres/Neon connection string. Use the **pooled** endpoint (host contains `-pooler`) |
| `MODEL_IQ_BASE_URL` / `MODEL_IQ_API_KEY` | yes | — | The OpenAI-compatible gateway powering the advisor agent |
| `JUPITER_AGENT_API_KEY` | yes | — | The member identity the agent acts as |
| `JUPITER_LOCK_TTL` | no | `300` | Seconds an unrefreshed claim survives. Floor 5. Session TTL is `max(2 × this, 600)` |
| `JUPITER_KEY_PEPPER` | no | — | Upgrades stored key digests to HMAC-SHA-256 |
| `JUPITER_STORE_SNIPPETS` | no | off | Store the claimed lines' source so conflicts can show the code. Read the warning above before enabling |
| `JUPITER_LLM_API_KEY` | no | `MODEL_IQ_API_KEY` | Overrides the gateway used for overlap analysis |
| `JUPITER_LLM_MODEL` | no | `glm-5-3` | Any model your gateway serves |
| `JUPITER_LLM_ENABLED` | no | — | Set to `false` to force overlap analysis off without removing keys |

A Jupiter key is a **256-bit random token**, stored as a SHA-256 digest and compared in constant
time. Set `JUPITER_KEY_PEPPER` to upgrade the digest to HMAC-SHA-256, so a read-only leak of the
database alone yields nothing verifiable. Changing or removing the pepper invalidates every
existing key — set it before you hand keys out, or not at all.

## What this does not do

These are the trust model of a tool meant for a trusted team network. Read this before putting
Jupiter on a public address.

- **Joining is open.** Anyone who can reach the server and knows a team's slug can join it and get
  a member key. There is no invitation and no approval.
- **No key rotation or revocation.** A leaked key is valid until the team is abandoned.
- **No rate limiting.**
- **Claim history is not an audit log.** `/api/history` shows every claim ever taken, which is a
  record of intent, not of access — nothing logs who *read* the dashboard, called a tool, or
  fetched a snippet. The rows are ordinary mutable table rows, and `state` is inferred rather
  than recorded. Any member can read the whole org's history, so it also widens what a leaked
  key exposes: not just what is claimed now, but everything anyone has claimed.
- **A blocked claim is still recorded**, so a block "lifts" when the other claim expires without
  anyone being told. That is the advisory design, not a defect.
- **The SSE stream authenticates with a `?key=` query parameter**, because `EventSource` cannot
  set headers. A URL is likelier than a header to be captured in a log or shell history.
- **With overlap analysis enabled, claim metadata leaves your network.** Paths, intents, holder
  names and notes go to whatever gateway you configure. No file contents do, but a repo's file
  tree and what people are working on can itself be sensitive.
- **With `JUPITER_STORE_SNIPPETS` enabled, your database holds source code.** Combined with open
  joining and no key revocation, that means anyone who learns a team's slug can read the claimed
  lines of everyone's code, and a read-only leak of the database exposes source rather than just
  filenames. Snippets never reach the model, but they are readable by any member of the org. It is
  off by default; turn it on only where that trade is acceptable, and not for client code.
- **`/api/mcp/{key}` accepts a key in the path** as a labelled fallback for
  [Claude Code #29562](https://github.com/anthropics/claude-code/issues/29562) and
  [#50464](https://github.com/anthropics/claude-code/issues/50464), where `--header` is not
  forwarded to an HTTP MCP server. Prefer the header form.

## Layout

```
workflow.yaml     the advisor agent — model, system prompt, tools, middleware
tools/            the agent's tools, over jupiter_core
advisor.py        adapts the agent to jupiter_core's `analyze` seam
app.py            FastAPI: REST + SSE + MCP mount + static + agent WebSocket
api/              route handlers — parse → auth → call jupiter_core → JSON
jupiter_core/     all the logic, framework-free
  paths.py        path normalisation        expiry: time_util.py + sweep.py
  auth.py         key minting and verification   locks_repo.py  the conflict rule,
                                                 and the history query beside it
  activity.py     the single batched query   semantic.py  analysis + validation
  render.py       the exact tool output strings
mcp_app/          the MCP server (official mcp SDK, transport-level bearer auth)
jupiter_admin/    bootstrap CLI
ui_source/        dashboard source (Vite + React + Tailwind)
static/           built dashboard
tests/            150 unit tests — no database, no network
```

`jupiter_core/` imports neither FastAPI, nor AgentFlow, nor the `mcp` SDK. All three front doors —
the agent, the REST API, and the MCP server — call the same functions, so there is exactly one
implementation of the coordination rules.

## Tests

```bash
pytest tests/          # 150 tests, fully offline
```

Covers path normalisation (separators, `.`/`..`, NFC, control characters, the length cap, and that
case sensitivity is *preserved*); key mint→parse→verify round trips, underscores inside a secret,
an empty hash never verifying, an oversized id giving 401 rather than 500; the full conflict
matrix; TTL arithmetic at the boundary; every rendered string; and the semantic validator driven
with every way a model can be wrong — a hallucinated path, a group that is really one person's
work, a missing reason, a junk confidence, a reply that isn't the right shape at all — asserting
each is dropped.

The line-range suite pins the property the feature rests on: a claim with no range covers the
whole file, so it conflicts with everything on that path and renders byte-identically to how
claims read before ranges existed. It also drives the overlap matrix (partial, touching,
adjacent-but-disjoint, contained, identical), the validation rejections, and that snippets are
dropped unless storage is explicitly enabled.

The history suite covers the `expired`/`released` boundary in both directions, that the inference
follows the configured TTL rather than the default, that a row with no `refreshed_at` is never
called expired, and that `HistoryLockOut` and `LockOut` agree on every field they share — plus
that the two queries select the same columns in the same order, since both feed one positional
row mapper.

Integration tests that need a real database are gated behind `JUPITER_TEST_DATABASE_URL` and skip
when it is unset: the lazy-sweep SQL uses `interval`, `ON CONFLICT … WHERE` and a correlated
`EXISTS` against `now()` that SQLite does not support the same way.

## Development notes

- **Windows:** `psycopg`'s async mode needs a `SelectorEventLoop`, and `uvicorn.run()` hardcodes
  `ProactorEventLoop` there regardless of the ambient asyncio policy. `app.py`'s `__main__` block
  drives the server manually with a selector loop on `win32`; `python app.py` is correct on every
  platform.
- **Migrations:** raw idempotent SQL in `jupiter_core/db.py:SCHEMA_SQL`, applied by
  `jupiter_admin db-push`. No migration framework, on purpose.
- **UI:** `cd ui_source && npm install && npm run build` — output goes to `static/`.

## Licence

MIT.
