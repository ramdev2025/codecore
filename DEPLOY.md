# Deploying Jupiter

Target: **https://jupiter.workmov.com**, running on Fly.io in Singapore, with
DNS on Cloudflare.

## Why this shape

Jupiter is a single Python process holding state that cannot be load-balanced away:
the MCP `StreamableHTTPSessionManager` keeps session state in memory, the dashboard
holds an open SSE stream, and the advisor runs over a WebSocket. That rules out
serverless — Cloudflare Workers is a JS/Wasm runtime and cannot load `psycopg`'s
native extension, and GitHub Pages serves static files only. It needs a container
with a long-lived process.

Singapore because the Neon database is in `ap-southeast-1`; every request makes
several round trips to it.

## Prerequisites

Docker is **not** needed locally — Fly builds the image remotely.

```powershell
# flyctl
iwr https://fly.io/install.ps1 -useb | iex
fly auth signup      # or: fly auth login
```

## 1. Create the app and set secrets

`fly.toml` is already written, so create the app by name rather than letting
`fly launch` generate a new config.

```powershell
fly apps create jupiter-workmov
```

Secrets come from your local `.env` — never commit them. Set all four in one
command, so the app restarts once rather than four times:

```powershell
fly secrets set `
  DATABASE_URL="postgresql://...-pooler.../...?sslmode=require" `
  MODEL_IQ_BASE_URL="https://model-iq.aicore.accenture.com/v1" `
  MODEL_IQ_API_KEY="..." `
  JUPITER_AGENT_API_KEY="jpm_..."
```

Two notes on configuration:

- Use the **pooled** Neon endpoint — the host must contain `-pooler`. The direct
  endpoint will exhaust connections.
- Do **not** set `JUPITER_KEY_PEPPER` now. It changes how key digests are
  computed, so adding it would invalidate every key you have already minted,
  including `JUPITER_AGENT_API_KEY`.

The database schema already exists. Against a fresh database you would first run
`python -m jupiter_admin db-push` locally, pointed at it.

## 2. Deploy

```powershell
fly deploy
fly logs
```

Check it came up:

```powershell
curl https://jupiter-workmov.fly.dev/api/healthz
# {"status":"ok","version":"...","lock_ttl_seconds":300}
```

## 3. Point workmov.com at it

In **Cloudflare → DNS** for `workmov.com`, add:

| Type | Name | Target | Proxy |
|---|---|---|---|
| CNAME | `jupiter` | `jupiter-workmov.fly.dev` | **DNS only (grey)** |

Grey cloud, not orange — at least to start. Proxying breaks Fly's HTTP-01 ACME
challenge, so the certificate never issues, and Cloudflare's proxy can buffer
Server-Sent Events, which is exactly what the dashboard's live activity feed
depends on. Grey cloud avoids both problems and Fly still serves valid TLS.

Then issue the certificate:

```powershell
fly certs add jupiter.workmov.com
fly certs show jupiter.workmov.com     # wait for "Ready"
```

Usually under a minute. Then https://jupiter.workmov.com is live.

### Turning the proxy on later (optional)

If you want Cloudflare's DDoS protection and origin-IP hiding, switch the record
to orange **after** the certificate is `Ready`, and set **SSL/TLS → Overview →
Full (strict)**. Not Flexible — Flexible causes a redirect loop. Then reload the
dashboard and confirm the activity feed still streams; if events arrive in bursts
instead of live, Cloudflare is buffering the SSE and you should go back to grey.

One caution specific to this zone: `workmov.com` already serves a proxied site at
its apex, and **Cloudflare's SSL/TLS mode is zone-wide, not per-record**. Changing
it to Full (strict) for Jupiter also changes it for that existing site, which will
break it if its origin does not present a valid certificate. Check what the apex
origin is before touching the mode. Staying on grey cloud avoids the question
entirely — unproxied records bypass Cloudflare, so the zone mode never applies to
them.

## 4. Deploy on push (optional)

`.github/workflows/deploy.yml` runs the 130 offline tests and then deploys on
every push to `main`.

```powershell
gh repo create jupiter --private --source=. --remote=origin --push
```

**Private, not public.** The repo contains `agentflow-0.28.0-py3-none-any.whl`, an
internal Accenture artifact, and the internal Model IQ gateway URL.

Then give the workflow a deploy token:

```powershell
fly tokens create deploy -x 999999h
gh secret set FLY_API_TOKEN     # paste the token
```

## 5. Point teammates at it

From the dashboard's setup wizard, or directly:

```bash
claude mcp add --transport http jupiter --scope user \
  https://jupiter.workmov.com/api/mcp \
  --header "Authorization: Bearer jpm_..."
```

## Operating it

```powershell
fly logs                      # live
fly status                    # machine health
fly ssh console               # shell into the running container
fly secrets list              # names and digests, never values
fly deploy                    # redeploy from local source
```

**Never scale to more than one machine.** MCP session state lives in memory, so a
second machine would strand half the sessions on the wrong process. `fly.toml`
pins `min_machines_running = 1` with `auto_stop_machines = 'off'` for the same
reason — a suspended machine drops every open SSE stream and MCP session.

If you need more capacity, make the machine bigger:

```powershell
fly scale vm shared-cpu-2x --memory 2048
```

## What you are accepting by making this public

From the README's *What this does not do*, now that this is on an address anyone
can reach:

- **Joining is open.** Anyone who reaches the server and knows a team's slug can
  join it and mint themselves a member key. No invitation, no approval.
- **Keys cannot be revoked.** A leaked key is valid until the org is abandoned.
- **No rate limiting and no audit log.**
- **Claim metadata leaves your network** — paths, intents, holder names and notes
  go to the Model IQ gateway for overlap analysis. No file contents do, but a
  repo's file tree is itself informative. Set `JUPITER_LLM_ENABLED=false` to turn
  this off.
- Leave `JUPITER_STORE_SNIPPETS` off. Combined with open joining, enabling it
  would let anyone who learns a slug read the claimed lines of your source.

That trade is fine for a demo or a portfolio piece. Before putting real client
work behind it, put Cloudflare Access in front of `/static/*` and the browser API
routes, with `/api/mcp` bypassed so Claude Code can still connect on its bearer
token.
