"""Semantic overlap detection - the optional LLM feature.

Ported from jupiter-code's lib/semantic.ts and lib/llm.ts.

The deterministic rule in `locks_repo.py` catches two people on the *same*
path. This catches the other half: two people on *different* files whose
work probably collides anyway.

Only file paths, intents, holder names and short notes are ever sent to the
gateway. No file contents ever leave the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import httpx

from .locks_repo import ActiveLock, RelatedOut
from .time_util import isoformat, now as utcnow

MAX_OVERLAPS = 8
MAX_CLAIMS = 60
REASON_LIMIT = 240
CONFIDENCES = ("high", "medium", "low")

INFLIGHT_TIMEOUT_SECONDS = 60
CACHE_TTL_HOURS = 2

DEFAULT_BASE_URL = "https://model-iq.aicore.accenture.com/v1"
DEFAULT_MODEL = "glm-5-3"
DEFAULT_TIMEOUT_SECONDS = 20.0

# First match wins, so an explicit JUPITER_LLM_* always beats a fallback.
# MODEL_IQ_* (with the underscore) is what Weaver writes into .env for the
# agent's own gateway; MODELIQ_* (without) is what older deployments used, and
# MODEILIQ_MODEL is a typo carried forward deliberately so existing configs
# keep working.
KEY_VARS = (
    "JUPITER_LLM_API_KEY",
    "OPENAI_API_KEY",
    "MODELIQ_API_KEY",
    "MODEL_IQ_API_KEY",
    "API_KEY",
)
MODEL_VARS = ("JUPITER_LLM_MODEL", "MODELIQ_MODEL", "MODEILIQ_MODEL", "MODEL_IQ_MODEL")
BASE_VARS = ("JUPITER_LLM_BASE_URL", "OPENAI_BASE_URL", "MODEL_IQ_BASE_URL")

_PLACEHOLDER = re.compile(r"^(sk-(miq-)?)?<.*>$|^(your|changeme|replace|xxx)", re.IGNORECASE)

SYSTEM_PROMPT = """You review a software team's in-progress file claims and spot pairs or small groups of DIFFERENT files, held by DIFFERENT people, whose work is likely to collide even though the paths differ.

Report a group only when there is a concrete, nameable reason, such as:
- an implementation and its test file
- a data model and a migration, schema, or fixture for it
- a caller and the function it calls
- two files that clearly implement two halves of one feature
- a config/route definition and the handler it wires up

Do NOT report:
- two claims on the same path (handled elsewhere, and reporting it is an error)
- files that merely sit in the same directory with no real relationship
- groups where every claim belongs to the same person
- speculation you cannot justify in one short sentence

Precision matters far more than recall. An empty list is the correct and expected answer when nothing clearly overlaps - do not invent findings.

Reply with strict JSON only, in exactly this shape:
{"overlaps": [{"paths": ["a", "b"], "reason": "one short sentence", "confidence": "high"}]}

"confidence" must be one of "high", "medium", "low". Every string in "paths" must be copied character-for-character from the input."""


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class AnalysisClaim:
    file_path: str
    intent: str
    member: str
    member_id: int
    note: str | None


def claims_for_analysis(locks: list[ActiveLock]) -> list[AnalysisClaim]:
    return [
        AnalysisClaim(
            file_path=lock.file_path,
            intent=lock.intent,
            member=lock.member,
            member_id=lock.member_id,
            note=lock.note,
        )
        for lock in locks
    ]


def fingerprint(claims: list[AnalysisClaim]) -> str:
    """Stable id for a set of claims - the cache key.

    Built from the fields the model actually sees, so a pure TTL refresh
    (which changes only timestamps) does not invalidate a good answer.
    """
    rows = sorted(
        json.dumps([c.file_path, c.intent or "", str(c.member_id or ""), c.note or ""])
        for c in claims
    )
    digest = hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()
    return digest[:16]


def _worth_analysing(claims: list[AnalysisClaim]) -> bool:
    paths = {c.file_path for c in claims}
    members = {c.member_id for c in claims}
    return len(paths) >= 2 and len(members) >= 2


def validate_overlaps(reply: dict, claims: list[AnalysisClaim]) -> list[RelatedOut]:
    """Keep only findings that check out against the real claim set.

    Everything the model says is a suggestion to be checked, never data to
    be believed.
    """
    raw = reply.get("overlaps")
    if not isinstance(raw, list):
        return []

    by_path: dict[str, list[AnalysisClaim]] = {}
    for claim in claims:
        by_path.setdefault(claim.file_path, []).append(claim)

    out: list[RelatedOut] = []
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue

        paths = item.get("paths")
        if not isinstance(paths, list):
            continue

        clean = []
        seen_path = set()
        for p in paths:
            if isinstance(p, str) and p not in seen_path and p in by_path:
                seen_path.add(p)
                clean.append(p)
        if len(clean) < 2:
            continue

        holders: set[str] = set()
        holder_ids: set[int] = set()
        for path in clean:
            for claim in by_path.get(path, []):
                holders.add(claim.member)
                holder_ids.add(claim.member_id)
        if len(holder_ids) < 2:
            continue

        reason = item.get("reason")
        reason = reason.strip()[:REASON_LIMIT] if isinstance(reason, str) else ""
        if not reason:
            continue

        raw_confidence = item.get("confidence")
        raw_confidence = raw_confidence.strip().lower() if isinstance(raw_confidence, str) else ""
        confidence = raw_confidence if raw_confidence in CONFIDENCES else "medium"

        key = "\u0000".join(sorted(clean))
        if key in seen:
            continue
        seen.add(key)

        out.append(RelatedOut(paths=clean, members=sorted(holders), reason=reason, confidence=confidence))
        if len(out) >= MAX_OVERLAPS:
            break

    return out


def build_prompt(claims: list[AnalysisClaim]) -> str:
    lines = ["Active file claims:"]
    for claim in claims[:MAX_CLAIMS]:
        note = f" - note: {claim.note}" if claim.note else ""
        lines.append(f"- {claim.file_path} | {claim.intent or 'editing'} | held by {claim.member}{note}")
    lines.append("")
    lines.append("Which of these different files are likely to collide? JSON only.")
    return "\n".join(lines)


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    api_key: str | None
    model: str
    base_url: str
    forced_off: bool


@dataclass(frozen=True)
class LLMStatus:
    enabled: bool
    model: str | None
    base_url: str | None
    reason: str | None


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value and not _PLACEHOLDER.match(value):
            return value
    return None


def llm_config() -> LLMConfig:
    api_key = _first_env(KEY_VARS)
    switch_value = (os.environ.get("JUPITER_LLM_ENABLED") or "").strip().lower()
    forced_off = switch_value in ("0", "false", "no", "off")
    base_url = (_first_env(BASE_VARS) or DEFAULT_BASE_URL).rstrip("/")
    return LLMConfig(
        enabled=bool(api_key) and not forced_off,
        api_key=api_key,
        model=_first_env(MODEL_VARS) or DEFAULT_MODEL,
        base_url=base_url,
        forced_off=forced_off,
    )


def describe_llm(config: LLMConfig | None = None) -> LLMStatus:
    config = config or llm_config()
    return LLMStatus(
        enabled=config.enabled,
        model=config.model if config.enabled else None,
        base_url=config.base_url if config.enabled else None,
        reason=(
            None
            if config.enabled
            else "disabled by JUPITER_LLM_ENABLED"
            if config.forced_off
            else "no API key configured (set JUPITER_LLM_API_KEY)"
        ),
    )


_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


def _parse_json_reply(content: str) -> dict:
    text = (content or "").strip()

    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("model reply contained no JSON object")
        text = text[start : end + 1]

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMError("model reply was not valid JSON") from error
    if not isinstance(parsed, dict):
        raise LLMError("model reply was not a JSON object")
    return parsed


async def chat_json(
    system: str,
    user: str,
    max_tokens: int = 1200,
    temperature: float = 0,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Run one completion and return its parsed JSON object.

    Retries once without `response_format` on HTTP 400 (some gateways
    reject it).
    """
    config = llm_config()
    if not config.enabled:
        raise LLMError("no LLM configured")

    def body(with_json_mode: bool) -> dict:
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if with_json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    headers = {
        "authorization": f"Bearer {config.api_key}",
        "content-type": "application/json",
    }
    url = f"{config.base_url}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body(True))
            if response.status_code == 400:
                response = await client.post(url, headers=headers, json=body(False))
    except httpx.HTTPError as error:
        raise LLMError(f"cannot reach the LLM gateway ({type(error).__name__})") from error

    if response.status_code >= 400:
        raise LLMError(f"LLM gateway returned {response.status_code}: {response.text[:200]}")

    try:
        payload = response.json()
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as error:
        raise LLMError("unexpected response shape from the LLM gateway") from error

    return _parse_json_reply(content)


@dataclass(frozen=True)
class SemanticOut:
    status: str  # "ready" | "pending" | "disabled" | "error"
    overlaps: list[RelatedOut]
    analyzed_at: str | None
    model: str | None
    error: str | None
    llm: LLMStatus


def _row_to_result(row) -> SemanticOut:
    status, findings, model, error, analyzed_at = row
    overlaps = [RelatedOut(**f) for f in findings] if isinstance(findings, list) else []
    return SemanticOut(
        status=status or "error",
        overlaps=overlaps,
        analyzed_at=isoformat(analyzed_at),
        model=model,
        error=error,
        llm=describe_llm(),
    )


def _empty_ready(model: str | None) -> SemanticOut:
    return SemanticOut(status="ready", overlaps=[], analyzed_at=isoformat(utcnow()), model=model, error=None, llm=describe_llm())


def _disabled() -> SemanticOut:
    llm = describe_llm()
    return SemanticOut(status="disabled", overlaps=[], analyzed_at=None, model=None, error=llm.reason, llm=llm)


async def peek_cached_overlaps(aconn, org_id: int, claims: list[AnalysisClaim]) -> list[RelatedOut] | None:
    """Cached overlaps for this claim set, or None. Never calls the gateway."""
    config = llm_config()
    if not config.enabled or not _worth_analysing(claims):
        return None

    key = fingerprint(claims)
    async with aconn.cursor() as cur:
        await cur.execute(
            "SELECT findings FROM semantic_cache WHERE org_id = %s AND fingerprint = %s AND status = 'ready'",
            (org_id, key),
        )
        row = await cur.fetchone()

    if row is None or not isinstance(row[0], list):
        return None
    return [RelatedOut(**f) for f in row[0]]


async def _default_analyze(claims: list[AnalysisClaim]) -> dict:
    """Fallback analyzer: one direct call to an OpenAI-compatible gateway.

    Used when no analyzer is injected. The app injects an AgentFlow-backed
    one instead (see `advisor.py`) — this keeps `jupiter_core` free of any
    AgentFlow import while still letting the agent own the reasoning in
    production.
    """
    return await chat_json(SYSTEM_PROMPT, build_prompt(claims))


async def get_semantic(
    aconn,
    org_id: int,
    claims: list[AnalysisClaim],
    analyze: Callable[[list[AnalysisClaim]], Awaitable[dict]] | None = None,
) -> SemanticOut:
    """The analysis for `claims`, running it if nobody else already is.

    Single-flight via `semantic_cache`: whoever wins the `INSERT ... ON
    CONFLICT ... WHERE` claims the fingerprint and runs the analysis inline;
    everyone else sees `pending`.

    `analyze` maps the claim set to the model's raw reply. Whatever it
    returns is still put through `validate_overlaps` — the distrust ladder
    applies identically no matter who produced the reply.
    """
    config = llm_config()
    if not config.enabled:
        return _disabled()
    if not _worth_analysing(claims):
        return _empty_ready(config.model)

    key = fingerprint(claims)

    async with aconn.cursor() as cur:
        await cur.execute(
            """
            SELECT status, findings, model, error, analyzed_at, started_at
              FROM semantic_cache
             WHERE org_id = %s AND fingerprint = %s
            """,
            (org_id, key),
        )
        existing = await cur.fetchone()

    if existing is not None and existing[0] != "pending":
        return _row_to_result(existing[:5])

    async with aconn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO semantic_cache (org_id, fingerprint, status, model, started_at)
            VALUES (%s, %s, 'pending', %s, now())
            ON CONFLICT (org_id, fingerprint) DO UPDATE
               SET started_at = now(), status = 'pending', error = NULL
             WHERE semantic_cache.started_at < now() - %s
            RETURNING id
            """,
            (org_id, key, config.model, timedelta(seconds=INFLIGHT_TIMEOUT_SECONDS)),
        )
        claimed = await cur.fetchone()

    if claimed is None:
        return SemanticOut(
            status="pending", overlaps=[], analyzed_at=None, model=config.model, error=None,
            llm=describe_llm(config),
        )

    status = "ready"
    overlaps: list[RelatedOut] = []
    error: str | None = None

    try:
        reply = await (analyze or _default_analyze)(claims)
        overlaps = validate_overlaps(reply, claims)
    except Exception as caught:
        status = "error"
        error = str(caught) if isinstance(caught, LLMError) else f"{type(caught).__name__}: {caught}"

    now = utcnow()
    async with aconn.cursor() as cur:
        await cur.execute(
            """
            UPDATE semantic_cache
               SET status = %s, findings = %s::jsonb, error = %s, model = %s, analyzed_at = %s
             WHERE org_id = %s AND fingerprint = %s
            """,
            (
                status,
                json.dumps([o.__dict__ for o in overlaps]),
                error,
                config.model,
                now,
                org_id,
                key,
            ),
        )
        await cur.execute(
            "DELETE FROM semantic_cache WHERE org_id = %s AND started_at < now() - %s",
            (org_id, timedelta(hours=CACHE_TTL_HOURS)),
        )

    return SemanticOut(status=status, overlaps=overlaps, analyzed_at=isoformat(now), model=config.model, error=error, llm=describe_llm(config))


def related_for(overlaps: list[RelatedOut] | None, file_path: str, display_name: str | None) -> list[RelatedOut]:
    """Overlaps touching `file_path` that are held by someone other than us."""
    if not overlaps:
        return []

    out: list[RelatedOut] = []
    for overlap in overlaps:
        if file_path not in overlap.paths:
            continue
        others = [p for p in overlap.paths if p != file_path]
        holders = [m for m in overlap.members if m != display_name]
        if others and holders:
            out.append(RelatedOut(paths=others, members=holders, reason=overlap.reason, confidence=overlap.confidence))
    return out
