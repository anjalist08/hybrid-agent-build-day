# Hybrid Agent Build Day

Project for **Hybrid AI in Action: From Personal Agents to Real-World Deployment Build Day**
(Lenovo × AGI House, Sunday Nov 8, 2026).

> **Project idea:** _TBD — fill in once the team picks one._

## The problem space

Hybrid AI: deciding what a personal agent runs **on-device**, at the **edge**, and in the
**cloud**, and making those handoffs invisible. Personal context stays on hardware you own,
the agent keeps working when the connection drops, and frontier cloud models are called only
when the task needs them.

## Today's timeline

| Time     | What                                                     |
| -------- | -------------------------------------------------------- |
| 12:15 PM | Building starts                                          |
| 4:00 PM  | Project check-in with the AGI House team                 |
| 7:00 PM  | **Save project draft**: finalists are picked from this   |
| 8:00 PM  | Demos, judging, awards                                   |

Prizes: $5,000 / $3,000 / $2,000.

## Idea shortlist (from the AGI House research brief)

**Routing and hybrid systems**
- **The visible router**: assistant with a live panel showing where each request ran, why, and its cost. Beginner-friendly.
- **Ask before you escalate**: local model answers several times and escalates to the cloud only when it disagrees with itself (CARGO-style).
- **Step-level handoff**: escalate individual uncertain agent steps instead of whole tasks (STEPGATE-style).
- **Cloud plans, local reads**: Minions-style; the cloud writes instructions, local models read the raw documents.
- **Unplug test**: assistant that degrades gracefully when the network drops, then syncs.

**Local-first personal agents**
- **Private inbox triage**: raw mail stays local; only redacted summaries go to the cloud.
- **Morning brief, on-device**: overnight briefing from calendar and notes, all local.
- **Personal knowledge agent**: Q&A over your files with citations; cloud only for heavy reasoning.
- **Local hands, cloud backup**: on-device computer-use agent (Fara-7B) that asks the cloud for help on unfamiliar sites.
- **Memory that follows you**: shared private memory across laptop, phone, and desk-side box.

**The AI server under your desk**
- **Small law firm on one box**: multi-user assistant on a ThinkStation PGX; privileged text never leaves.

Useful stacks: Ollama / LM Studio / vLLM, small open models (Qwen, Gemma, Liquid LFM),
OpenJarvis, Hermes Agent, any cloud model API.

## Repo layout

```
docs/      notes, demo script, architecture sketches
```
