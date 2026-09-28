"""The AgentFlow-backed semantic analyzer.

`jupiter_core` deliberately imports no AgentFlow — it is pure business logic
plus a Postgres driver. So the coupling runs the other way: this module
adapts the advisor agent to the `analyze` seam that
`jupiter_core.semantic.get_semantic` accepts, and `app.py` injects it.

What the agent produces is NOT trusted. Its reply goes through the exact
same `validate_overlaps` ladder as any other reply: invented paths are
dropped, a group that is really one person's own work is dropped, a finding
with no reason is dropped, holders are read from our own data and never from
the model. The agent decides what to *suggest*; the validator decides what
survives.
"""

from __future__ import annotations

import json

from jupiter_core.semantic import (
    SYSTEM_PROMPT,
    AnalysisClaim,
    LLMError,
    _parse_json_reply,
    build_prompt,
)

_ORCHESTRATOR = None


def set_orchestrator(orchestrator) -> None:
    """Called once from app.py's lifespan."""
    global _ORCHESTRATOR
    _ORCHESTRATOR = orchestrator


async def analyze_with_agent(claims: list[AnalysisClaim]) -> dict:
    """Ask the advisor agent for overlap candidates; return its raw JSON reply.

    Raises LLMError so `get_semantic` records it as a normal analysis error
    rather than a crash — the semantic layer is advisory and must never take
    the rest of Jupiter down with it.
    """
    if _ORCHESTRATOR is None:
        raise LLMError("advisor agent is not running")

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        "Analyse the claim set below and reply with ONLY the JSON object "
        '{"overlaps": [...]} — no prose, no code fence.\n\n'
        f"{build_prompt(claims)}"
    )

    state = {"messages": [{"role": "user", "content": prompt}]}
    config = {"thread_id": "semantic-analysis"}

    chunks: list[str] = []
    try:
        async for event in _ORCHESTRATOR.run(state, config=config, stream_tokens=False):
            if event.get("type") != "agent":
                continue
            content = event.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            if content:
                chunks.append(str(content))
    except Exception as error:
        raise LLMError(f"advisor agent failed ({type(error).__name__})") from error

    if not chunks:
        raise LLMError("advisor agent returned nothing")

    return _parse_json_reply(chunks[-1])


def analysis_payload(claims: list[AnalysisClaim]) -> str:
    """The exact text handed to the model — paths, intents, holders, notes.

    Never file contents. Exposed so the Settings page can show operators
    precisely what leaves their network.
    """
    return json.dumps(
        [
            {"file_path": c.file_path, "intent": c.intent, "holder": c.member, "note": c.note}
            for c in claims
        ],
        indent=2,
    )
