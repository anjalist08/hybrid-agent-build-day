# Build notes

## Decisions

- **Project: Lens.** iPhone screen capture → private knowledge base → voice Q&A with generated native UI.
- **Screen capture:** ReplayKit Broadcast Upload Extension, started by the user (red pill is fine).
  One JPEG every 5s at ~1280px. No in-app tap capture; understanding is purely visual.
- **Extraction is local:** Ollama `qwen2.5vl:7b`, ~12–15s per new screen on an M-series Mac.
  Identical screens are deduped by perceptual hash and only add dwell time (no model call).
  Cloud extraction is opt-in (`LENS_EXTRACTOR=claude` or `LENS_CLOUD_FALLBACK=true`).
- **Privacy:** frames flagged `sensitive` (banking, DMs, passwords) are dropped. JPEGs are not
  stored unless `LENS_SAVE_FRAMES=true`. `/query` sends Claude text rows only (logged as "0 images").
- **Answering:** `claude-opus-5-5`, effort `low` for voice latency, structured output
  `{speech, ui, action}`. Server-side refusal fallback is enabled (`fallbacks: "default"`).
- **Generative UI:** our own flat JSON component catalog + SwiftUI renderer instead of an
  OpenUI library (no native Swift renderer exists for those).
- **Voice:**
  1. Hold-to-talk in the app: on-device STT → answer spoken with AVSpeechSynthesizer + UI rendered.
  2. "Hey Siri, ask Lens" App Intent: works while X/YouTube stays on screen; Siri speaks the
     answer and shows the generated UI as a snippet. Can be bound to the Action Button.
  No always-on wake word (iOS doesn't allow it for third-party apps).
- **Actions:** `open_url` only (deep link back to the video/post/profile). No control of other apps.

## Demo script

1. (30s) Problem: "I saw a great video about X last week… where was it?" Your phone has no memory.
2. Start capture (red pill). Scroll X for ~45s, watch a YouTube video about AI agents for ~45s.
3. Show the routing panel: every frame was read by the **local** model; duplicate screens skipped.
4. Hold mic: "What have I been watching about AI agents?" → spoken answer + timeline.
5. Go back to X. "Hey Siri, ask Lens" → "Who have I been reading the most?" → person card over X.
6. "Open the last video I watched" → YouTube opens.
7. Close on the hybrid table: pixels stay local, the cloud sees text only, and it's shown live in the app.

Fallback if the phone or network fails: `POST /ingest/video` with a pre-recorded screen recording,
then ask through the typed box or curl.

## Open questions

- Is the local model fast enough for the live demo? If not, lower the cadence or switch to `LENS_EXTRACTOR=claude` for the demo.
- Which team member's Apple developer account is used for signing (App Group must match the bundle prefix)?
- Should we add a "daily digest" push notification (stretch)?
