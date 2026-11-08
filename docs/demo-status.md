# Demo status — developer notes

The customer-facing local preview is `http://localhost:8000/demo`. It follows the supplied Figma concert CUJ, in English. It contains no developer badges, endpoint names, or fake-mode explanations. This file is the developer-facing disclosure.

## Working

- Real FastAPI HTTP requests, request validation, SQLite reads/writes, interest ranking, and route logs.
- Existing `/health`, `/interests`, `/impressions`, `/query`, and `/routes` protocols.
- Concert journey requests use `/demo/cuj` in fake mode only, with session-isolated SQLite state.
- Budget filtering, seated-only refinement, ticket selection, independent invitation/calendar confirmations, and remember/skip choices.
- Web DOM rendering and navigation. The local page is a web implementation of the mobile Figma flow, not a remotely controlled iPhone.
- Swift API integration and iOS simulator home connection were verified earlier; iOS uses the same existing memory endpoints. The new concert CUJ adapter is currently wired to the Web preview, not the native ticket flow.

## Fake / scripted

- Browsing history, creators, watch durations, concert, artist/venue/date availability, ticket options/prices, Mia's availability and contact details.
- Model answers and image understanding: fake mode uses deterministic rules and does not invoke Ollama or Claude. Uploaded frames are not analyzed.
- Voice interaction: the CUJ shows the designed listening/transcription state using a scripted request. Users can type a different request. No actual microphone recording or speech recognition runs in the Web preview.
- Search results: fixed ticket fixtures filtered by budget and seating. No provider is contacted.
- Send invite / Add to calendar: real local state transitions only; no email or calendar service is contacted.
- Remember: stored only in the isolated demo session table. It does not update real personal memory or model preferences.
- The concert photo is the actual image layer exported from the provided Figma file (`Live concert`, node `4:15206`), not a screenshot of a UI frame. The Web detail uses it in the design's 354 × 160 slot.

## Not connected to real external services

No actual ticket search, reservation, purchase, invitation delivery, calendar write, or production memory persistence. The ticket-listing review is an internal preview, without checkout.

## Not verified end to end

Real model inference, speech, ReplayKit screen capture on a physical iPhone, and physical-device networking. The earlier iOS code passes typechecking/compilation and simulator display checks; this does not establish a signed full-project build or physical-device validation.

## Run locally

```sh
cd backend
LENS_FAKE_MODE=true uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open `/demo`. The running preview uses `LENS_DATA_DIR=/tmp/lens-local-demo-data`. Both the page and CUJ endpoints are unavailable when fake mode is off. Sessions are isolated by a browser session ID; Restart creates a new session without clearing other sessions or the real knowledge base.
