"""The OpenUI agent: Claude reads a friends' group chat or email, pieces together the trip, and
streams OpenUI Lang screens: the trip plan to confirm, then flights + seats + stay + car + payment.

Wire format to the app: Server-Sent Events, one JSON object per `data:` line —
  {"type": "status", "status": "thinking" | "tool" | "writing", "tool"?: str}
  {"type": "delta", "text": str}       append to the OpenUI program being rendered
  {"type": "reset"}                    discard streamed text (a turn was re-issued)
  {"type": "done", "stop_reason": str}
  {"type": "error", "message": str}
Live data and bookings never run here: the generated UI calls them through /tools (Query/Mutation).
"""

import json
import logging
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import anthropic

from . import travel
from .config import settings

log = logging.getLogger("lens.agent")

PROMPT_PATH = Path(__file__).parent / "openui" / "system-prompt.md"
MAX_TOOL_ROUNDS = 3

# Server-side tools the model may call before writing UI (none needed: the UI fetches live data).
MODEL_TOOLS: list[dict] = []

_client: anthropic.Anthropic | None = None


def _claude() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _run_model_tool(name: str, args: object) -> tuple[str, bool]:
    return f"Unknown tool {name}", True


def _system() -> list[dict]:
    today = datetime.now().strftime("%A, %B %d, %Y")
    return [
        # The generated prompt is ~70 KB and identical on every request: cache it.
        {"type": "text", "text": PROMPT_PATH.read_text(), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Today is {today}. The user lives in San Francisco (home airport SFO). "
                                 "Answer with OpenUI Lang only (no Markdown fences, no prose outside the program)."},
    ]


def _debug_log(messages: list[dict], program: str, tools_used: list[str], ms: int) -> None:
    if not settings.debug_dump:
        return
    day = settings.debug_dir / datetime.now().strftime("%Y-%m-%d")
    day.mkdir(parents=True, exist_ok=True)
    last = messages[-1]["content"] if messages else ""
    with (day / "agent.md").open("a", encoding="utf-8") as f:
        f.write(f"## {datetime.now():%H:%M:%S} · {ms} ms · tools: {', '.join(tools_used) or 'none'}\n\n"
                f"**User:** {last}\n\n```openui-lang\n{program}\n```\n\n")


def stream(messages: list[dict], effort: str = "low") -> Iterator[dict]:
    """Yields wire events. `messages` is the chat so far: [{role, content: str}, ...]."""
    conversation: list[dict] = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("content")]
    start = time.perf_counter()
    program = ""
    tools_used: list[str] = []

    for round_ in range(MAX_TOOL_ROUNDS + 1):
        streamed_text = False
        try:
            with _claude().messages.stream(
                model=settings.claude_model,
                max_tokens=32000,
                output_config={"effort": effort},
                system=_system(),
                **({"tools": MODEL_TOOLS,
                    # After a few lookups, answer with what we have.
                    "tool_choice": {"type": "auto" if round_ < MAX_TOOL_ROUNDS else "none"}} if MODEL_TOOLS else {}),
                messages=conversation,
                extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
                extra_body={"fallbacks": "default"},
            ) as s:
                for event in s:
                    if event.type == "content_block_start":
                        kind = event.content_block.type
                        if kind in ("thinking", "redacted_thinking"):
                            yield {"type": "status", "status": "thinking"}
                        elif kind == "text":
                            yield {"type": "status", "status": "writing"}
                        elif kind == "tool_use":
                            yield {"type": "status", "status": "tool", "tool": event.content_block.name}
                    elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                        streamed_text = True
                        program += event.delta.text
                        yield {"type": "delta", "text": event.delta.text}
                message = s.get_final_message()
        except anthropic.APIError as e:
            log.exception("agent stream failed")
            yield {"type": "error", "message": f"Claude API error: {e}"}
            return

        if message.stop_reason == "refusal":
            yield {"type": "error", "message": "Claude declined this request."}
            return

        tool_uses = [b for b in message.content if b.type == "tool_use"]
        if message.stop_reason != "tool_use" or not tool_uses:
            ms = int((time.perf_counter() - start) * 1000)
            _debug_log(messages, program, tools_used, ms)
            log.info("agent answered in %d ms (tools: %s, %d chars)", ms, tools_used, len(program))
            yield {"type": "done", "stop_reason": message.stop_reason}
            return

        # Text before a tool call isn't part of the final program.
        if streamed_text:
            program = ""
            yield {"type": "reset"}
        conversation.append({"role": "assistant", "content": message.content})
        results = []
        for block in tool_uses:
            tools_used.append(block.name)
            content, is_error = _run_model_tool(block.name, block.input)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
        conversation.append({"role": "user", "content": results})

    yield {"type": "error", "message": "Too many tool rounds."}


def run_ui_tool(name: str, args: dict) -> dict:
    """Tools the generated UI calls through Query()/Mutation() (via POST /tools/{name})."""
    if name == "notify_friends":
        # Normally handled on the phone (opens Messages); this is the fallback for other clients.
        return {"status": "ok", "message": args.get("message", "")}
    fn = travel.TOOLS.get(name)
    if fn is None:
        raise travel.TravelError(f"Unknown tool '{name}'. Available: {', '.join(travel.TOOLS)}")
    try:
        return fn(**args)
    except TypeError as e:
        raise travel.TravelError(f"Bad arguments for {name}: {e}") from e
