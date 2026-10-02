/**
 * Typed client for the Jupiter REST API.
 *
 * Every /api call authenticates with `X-API-Key`. The SSE stream is the one
 * exception — EventSource cannot set headers, so it carries the key in the
 * query string instead (same-origin only; nothing else in the API accepts a
 * key that way).
 */

export interface LockOut {
  lock_id: number
  file_path: string
  intent: 'editing' | 'reading'
  member: string
  member_id: number
  session_id: number
  working_dir: string | null
  locked_at: string | null
  expires_at: string | null
  note: string | null
  /** null = the whole file is claimed, not a range. */
  line_start: number | null
  line_end: number | null
  /** Snippets are opt-in server-side, so this is false in most deployments. */
  has_snippet: boolean
}

/**
 * A claim from `/api/history` — live or long since closed.
 *
 * `state` is inferred server-side from how long the claim had gone
 * unrefreshed when it closed, because the sweep and an explicit unlock both
 * just stamp `released_at`. Treat it as a label, not a fact of record.
 */
export interface HistoryLockOut extends LockOut {
  released_at: string | null
  state: 'active' | 'expired' | 'released'
}

export interface HistoryOut {
  limit: number
  lock_ttl_seconds: number
  claims: HistoryLockOut[]
}

export interface SnippetOut {
  lock_id: number
  file_path: string
  line_start: number | null
  line_end: number | null
  code: string
  captured_at: string | null
}

export interface LockResponse {
  status: 'clear' | 'blocked'
  file_path: string
  intent: string
  expires_at: string | null
  conflicts: LockOut[]
  message: string
  related: OverlapOut[]
}

export interface AnnouncementOut {
  member: string
  message: string
  at: string | null
}

/** Who the API key making the request belongs to. Lets the UI say "you". */
export interface CallerOut {
  kind: 'member' | 'admin'
  member_id: number | null
  display_name: string | null
}

export interface ActivityOut {
  slug: string
  now: string | null
  lock_ttl_seconds: number
  locks: LockOut[]
  active_members: string[]
  announcements: AnnouncementOut[]
  me?: CallerOut | null
}

export interface MemberOut {
  member_id: number
  display_name: string
  joined_at: string | null
  active_sessions: number
  last_seen: string | null
}

export interface OverlapOut {
  paths: string[]
  members: string[]
  reason: string
  confidence: 'high' | 'medium' | 'low'
}

export interface LLMStatus {
  enabled: boolean
  model?: string | null
  base_url?: string | null
  reason?: string | null
}

export interface SemanticOut {
  status: 'ready' | 'pending' | 'disabled' | 'error'
  overlaps: OverlapOut[]
  analyzed_at: string | null
  model: string | null
  error: string | null
  llm: LLMStatus
}

export interface OrgCreated {
  org_id: number
  name: string
  slug: string
  admin_key: string
}

export interface MemberCreated {
  member_id: number
  display_name: string
  slug: string
  api_key: string
}

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.name = 'ApiError'
  }
}

const KEY_STORAGE = 'jupiter-api-key'

export function readStoredKey(): string | null {
  try {
    const raw = localStorage.getItem(KEY_STORAGE)
    return raw ? (JSON.parse(raw) as string) : null
  } catch {
    return null
  }
}

export function writeStoredKey(key: string | null) {
  try {
    if (key === null) localStorage.removeItem(KEY_STORAGE)
    else localStorage.setItem(KEY_STORAGE, JSON.stringify(key))
  } catch {
    /* private mode — the app still works for this session */
  }
}

async function request<T>(path: string, init: RequestInit = {}, key?: string | null): Promise<T> {
  const apiKey = key !== undefined ? key : readStoredKey()
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) }
  if (init.body) headers['Content-Type'] = 'application/json'
  if (apiKey) headers['X-API-Key'] = apiKey

  const res = await fetch(path, { ...init, headers })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  health: () => request<{ status: string; version?: string }>('/api/healthz'),

  createOrg: (name: string, slug?: string) =>
    request<OrgCreated>('/api/orgs', {
      method: 'POST',
      body: JSON.stringify(slug ? { name, slug } : { name }),
    }, null),

  joinOrg: (slug: string, display_name: string) =>
    request<MemberCreated>(`/api/orgs/${encodeURIComponent(slug)}/join`, {
      method: 'POST',
      body: JSON.stringify({ display_name }),
    }, null),

  members: (slug: string) =>
    request<MemberOut[]>(`/api/orgs/${encodeURIComponent(slug)}/members`),

  activity: () => request<ActivityOut>('/api/activity'),

  /**
   * Past claims, including ones that have already lapsed.
   *
   * `activity()` is deliberately a snapshot of the present and drops a claim
   * the instant it expires; this is how the Log page keeps a record of what
   * happened after the claim behind it is gone.
   */
  history: (limit = 200) => request<HistoryOut>(`/api/history?limit=${limit}`),

  announcements: (limit = 20) =>
    request<AnnouncementOut[]>(`/api/announcements?limit=${limit}`),

  postAnnouncement: (message: string) =>
    request<unknown>('/api/announcements', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  semantic: () => request<SemanticOut>('/api/semantic'),

  /**
   * The stored code for one claim's line range.
   *
   * Deliberately its own call rather than a field on LockOut: snippets stay
   * out of the bulk activity payload and off the SSE stream, so code is only
   * fetched at the moment someone opens a conflict.
   *
   * Throws ApiError(404) when nothing is stored — the normal case, since
   * snippet storage is opt-in server-side.
   */
  snippet: (lockId: number) => request<SnippetOut>(`/api/locks/${lockId}/snippet`),

  claim: (body: {
    session_id?: number
    file_path: string
    intent?: 'editing' | 'reading'
    note?: string
    line_start?: number
    line_end?: number
    code?: string
  }) => request<LockResponse>('/api/locks', { method: 'POST', body: JSON.stringify(body) }),
}

/** SSE URL for an org's live activity stream. */
export function streamUrl(slug: string, key: string): string {
  return `/api/orgs/${encodeURIComponent(slug)}/stream?key=${encodeURIComponent(key)}`
}

/** The command a teammate runs to point Claude Code at this deployment. */
export function mcpAddCommand(apiKey: string): string {
  return [
    'claude mcp add --transport http jupiter --scope user \\',
    `  ${window.location.origin}/api/mcp \\`,
    `  --header "Authorization: Bearer ${apiKey}"`,
  ].join('\n')
}
