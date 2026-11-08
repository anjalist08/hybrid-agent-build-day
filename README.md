# Hybrid Agent Build Day

Project for **Hybrid AI in Action: From Personal Agents to Real-World Deployment Build Day**
(Lenovo × AGI House, Sunday Nov 8, 2026).

> **Project: Lens** — a personal memory agent for your iPhone. It watches what you read and
> watch (X, YouTube, Medium, browsers) through screen capture, builds a private knowledge base
> of topics, people, and time spent, and answers spoken questions with a voice reply plus a
> natively rendered, model-generated UI. Screenshots are read by a **local** vision model;
> only extracted text ever reaches the **cloud** model.

## Lens: how it works

```
iPhone
 ├─ Broadcast Upload Extension (ReplayKit) ── JPEG every 5s ──────────────┐
 └─ Lens app (SwiftUI)                                                    │
     ├─ Hold-to-talk → on-device speech-to-text → POST /query ─────┐      │
     ├─ "Hey Siri, ask Lens" (App Intent, works over any app) ─────┤      │
     └─ speaks answer + renders generated UI  ◄────────────────────┤      │
                                                                   ▼      ▼
Laptop / desk box: FastAPI  (backend/)
 ├─ /ingest/frame → same-screen dedup (perceptual hash) → queue
 │     → LOCAL vision model (Ollama qwen2.5vl) → {app, items[title, author, topics]}
 │     → impressions with dwell time → entities (topics, people, apps) → interest scores
 ├─ /query → full-text retrieval + interests → CLOUD Claude (text only)
 │     → {speech, ui (component catalog), action}
 └─ /routes → log of where every step ran (local vs cloud, model, latency)
```

| Step | Runs where | Why |
|---|---|---|
| Speech-to-text, text-to-speech | iPhone | Instant and private |
| Screenshot understanding | Local vision model on the laptop | Raw pixels never leave hardware you own |
| Knowledge base | SQLite on the laptop | Your history stays on your machine |
| Answering + UI generation | Claude (cloud) | Needs strong reasoning; receives only titles, handles, topics, and dwell time |

### Run it

**Backend** (needs [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com)):

```bash
ollama pull qwen2.5vl:7b
cd backend
cp .env.example .env        # set ANTHROPIC_API_KEY
./run.sh                    # http://0.0.0.0:8000
uv run pytest -q            # offline tests
```

**iOS app** (needs Xcode 16 with the iOS platform installed, a paid Apple developer account, and a real iPhone; ReplayKit broadcast doesn't run in the Simulator):

```bash
brew install xcodegen
cd ios
cp Config/Local.xcconfig.example Config/Local.xcconfig   # team ID, bundle prefix, backend URL
xcodegen && open Lens.xcodeproj
```

Run the `Lens` scheme on the phone. Tap the red ● at the top, choose **Lens Capture**, then go use X or YouTube.
The phone and laptop must be able to reach each other: same Wi-Fi, or [Tailscale](https://tailscale.com) if the venue network blocks it.

**Demo fallback (no phone needed):** record your screen with the built-in iOS Screen Recording, AirDrop it to the laptop, and:

```bash
curl -F video=@recording.mp4 -F every_s=3 http://localhost:8000/ingest/video
curl -X POST localhost:8000/query -H 'content-type: application/json' -d '{"text":"what did I watch about AI?"}'
```

### Figma concert-flow preview

See [UI demo screenshots and walkthrough](docs/ui-demo.md).

The app now opens to a sample personal-suggestions screen. Tap **Take a look**,
then **Find tickets** to walk through disclosure, sample tickets, seated filtering,
invitation/calendar drafts, and a final plan. This flow runs locally with fictional
data; it does not search providers, purchase tickets, send messages, write calendar
events, or persist memory preferences. The fixed lock-screen time/date are design
fixtures. The waveform toolbar button opens the existing backend-connected voice
and text assistant; routing and settings remain available in the toolbar.

### Generative UI contract

The cloud model answers with a screen built from a small component catalog
(`header`, `text`, `card`, `list`, `timeline`, `person`, `chips`, `bar_chart`, `link_button`),
defined in [backend/app/schemas.py](backend/app/schemas.py) and rendered natively by
[ios/Lens/GenUI.swift](ios/Lens/GenUI.swift). Structured outputs guarantee the JSON matches.

### API

| Endpoint | What |
|---|---|
| `POST /ingest/frame` | multipart `frame` (JPEG), `ts`, `device` |
| `POST /ingest/video` | multipart `video`, `every_s`: demo fallback |
| `POST /query` | `{"text": "...", "source": "device-stt"}` → `{answer: {speech, ui, action}, route}` |
| `GET /impressions`, `/interests?type=topic`, `/routes`, `/health` | inspection |
| `DELETE /data` | wipe the knowledge base |

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
backend/   FastAPI service: ingest, local vision extraction, knowledge base, Claude queries
ios/       XcodeGen spec, SwiftUI app (Lens/), ReplayKit extension (LensBroadcast/), Shared/
docs/      notes, demo script, architecture sketches
```
