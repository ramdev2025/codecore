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

Deploy and verify on `jupiter-workmov.fly.dev` first. It already serves valid TLS
and involves Cloudflare not at all, so separating the two steps means a DNS
problem can never look like an app problem.

Two routes, depending on whether the record's proxy toggle will move.

### Route A — proxy stays on (orange cloud)

This works and needs no proxy toggle at all. Certificate validation moves onto
records Cloudflare *cannot* proxy, so the orange cloud on the traffic record stops
mattering.

1. Add the traffic record in **Cloudflare → DNS**:

   | Type | Name | Target | Proxy |
   |---|---|---|---|
   | CNAME | `jupiter` | `jupiter-workmov.fly.dev` | Proxied (orange) — fine |

2. Ask Fly which validation records it wants:

   ```powershell
   fly certs add jupiter.workmov.com
   fly certs setup jupiter.workmov.com
   ```

3. Add what it prints. There are two, and neither is proxyable:

   - a **`_fly-ownership` TXT** record — TXT records can never be proxied, so this
     one works regardless of any toggle
   - a **`_acme-challenge.jupiter` CNAME** pointing at Fly's target, which drives
     DNS-01 validation instead of the HTTP-01 challenge the proxy blocks

   Cloudflare's own guidance is that ownership-proving CNAMEs should not be
   proxied, so leave that one DNS-only if it offers the choice.

4. Set **SSL/TLS → Overview → Full (strict)**. Not Flexible — Flexible causes a
   redirect loop.

   **Check one thing before you do.** The mode is **zone-wide, not per-record**,
   and `workmov.com` already serves a proxied site at its apex. Switching the zone
   to Full (strict) also switches it for that site, and will break it if its origin
   does not present a valid certificate. Find out what the apex is first.

5. Wait for the certificate, then test the live feed:

   ```powershell
   fly certs show jupiter.workmov.com     # wait for "Ready"
   ```

   Open the dashboard and watch the activity feed. Cloudflare's proxy can buffer
   Server-Sent Events; if events arrive in bursts rather than continuously, that is
   what is happening, and Route B is the fix. WebSockets are supported on every
   Cloudflare plan, so the advisor panel is not at risk either way.

### Route B — DNS only (grey cloud)

Simpler where available: one CNAME with the proxy off, then `fly certs add`. No
ownership records, no zone-wide SSL change, no SSE buffering risk, and Fly serves
its own valid TLS.

If the toggle will not move, the record is usually managed by another Cloudflare
product — a Tunnel public hostname, a Workers custom domain, or a Pages project
each pin their record to proxied and grey the switch out. A record you add
yourself under a fresh subdomain is not subject to that, so add `jupiter` as a new
record rather than editing an existing one.

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
