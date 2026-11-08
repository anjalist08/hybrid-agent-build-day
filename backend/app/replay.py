"""Re-run extraction on frames saved in the debug folder, to compare models and prompts.

  uv run python -m app.replay data/debug/2026-11-08                    # default local model
  uv run python -m app.replay data/debug/2026-11-08 --model qwen2.5vl:3b
  uv run python -m app.replay data/debug/2026-11-08 --cloud            # CLAUDE_EXTRACT_MODEL

Writes <folder>/replay-<model>.md next to the frames and prints a timing summary.
"""

import argparse
import statistics
import time
from pathlib import Path

from .extract import extract_claude, extract_ollama, prepare_image


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--model", default=None, help="Ollama model (default: OLLAMA_VISION_MODEL)")
    ap.add_argument("--cloud", action="store_true", help="use Claude instead of Ollama")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    frames = sorted(args.folder.glob("*.jpg"))[: args.limit]
    if not frames:
        raise SystemExit(f"no .jpg frames in {args.folder}")
    fn = extract_claude if args.cloud else extract_ollama
    name = (args.model or ("cloud" if args.cloud else "default")).replace(":", "_").replace("/", "_")
    out = [f"# Replay with {args.model or ('cloud' if args.cloud else 'default model')}\n"]
    times, failures = [], 0
    for f in frames:
        jpeg = prepare_image(f.read_bytes())
        start = time.perf_counter()
        try:
            obs, _ = fn(jpeg, args.model)
            ms = int((time.perf_counter() - start) * 1000)
            times.append(ms)
            items = "\n".join(f"  - [{i.kind}] {i.title} — {i.author or '?'} ({', '.join(i.topics)})" for i in obs.items)
            out.append(f'## {f.name} · {obs.app} · {ms} ms\n<img src="{f.name}" width="200">\n\n{items or "  - (no items)"}\n')
            print(f"{f.name}: {ms:6d} ms  {obs.app:12s} {len(obs.items)} items")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{f.name}: FAILED {e!r}"[:200])
            out.append(f"## {f.name} · FAILED\n`{e!r}`\n")
    if times:
        summary = (f"{len(times)} ok, {failures} failed · median {statistics.median(times):.0f} ms · "
                   f"max {max(times)} ms")
        print(summary)
        out.insert(1, f"_{summary}_\n")
    (args.folder / f"replay-{name}.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
