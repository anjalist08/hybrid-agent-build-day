# Lens: Project Plan

Lenovo × AGI House **Hybrid AI Build Day**, Sunday Nov 8, 2026.
Deadlines: **save the project draft by 7:00 PM** (finalists are picked from it), **demo at 8:00 PM**.

The working code lives on the [`lens-mvp`](https://github.com/anjalist08/hybrid-agent-build-day/tree/lens-mvp) branch (built by Riaz).
This plan describes what we're building, what's done, what's left, and which tool does what.

---

## 1. The idea in one paragraph

**Lens is a memory for your phone.** It quietly watches what you read and watch on your
iPhone (X, YouTube, Medium, Safari), keeps a private log of topics, people and time spent,
and lets you ask about it out loud: *"What was that video about AI agents I watched?"*
It answers with a spoken reply and a screen built on the fly for that answer (a timeline,
a person card, a chart), and can open the post or video for you.

**Why it fits the hybrid AI theme:** the private part (your screen) is read by a model
running on hardware you own. Only short text (titles, handles, topics, time spent) ever
goes to the cloud model, which does the reasoning and designs the answer screen. The app
shows, live, where every step ran.

---

## 2. What the final product looks like

### What the user does
1. Opens Lens on the iPhone and taps the red **●** to start screen capture.
2. Uses the phone normally: scrolls X, watches YouTube, reads articles.
3. Asks a question in one of two ways:
   - **Hold the mic** in the Lens app and speak.
   - **"Hey Siri, ask Lens"** (or the **Action Button**) while still inside X or YouTube.
4. Hears a short spoken answer and sees a screen built for that answer.
5. Says or taps **"open it"** and the video, post or profile opens.

### What the judges see (8:00 PM demo, ~3 minutes)
1. **The problem (30s):** "I saw a great video about AI agents last week. Where was it?" Your phone has no memory.
2. **Capture:** start the red pill, scroll X and watch a YouTube video about AI agents.
3. **Where it ran:** open the routing panel. Every screenshot was read by the **local** model, and duplicate screens were skipped.
4. **Ask by voice:** "What have I been watching about AI agents?" → spoken answer + timeline.
5. **Ask from inside another app:** back in X, "Hey Siri, ask Lens: who have I been reading the most?" → person card over X.
6. **Act:** "Open the last video I watched" → YouTube opens.
7. **Close:** the hybrid table. Pixels stay local, the cloud sees text only, and the app proves it live.

**Fallback if the phone or network fails:** upload a pre-recorded screen recording to the
backend ahead of time and ask through the typed box.

### Example answer screens
| Question | Screen the model builds |
|---|---|
| "What did I watch about AI agents?" | Timeline of videos and posts, with time ago and time spent |
| "Who do I read most on X?" | Person card with their posts |
| "How much time on YouTube today?" | Bar chart by app |
| "What topics am I into lately?" | Topic chips |
| "Open the last video I watched" | Card + opens YouTube |

---

## 3. How it works

```
iPhone                                              Laptop (or desk-side box)
┌───────────────────────────────┐                   ┌─────────────────────────────────────────┐
│ Lens Capture (screen capture) │ ─ JPEG every 5s ─▶│ 1. Skip if same screen as last one      │
│                               │                   │ 2. LOCAL vision model reads the screen  │
│ Lens app                      │                   │    → app, titles, authors, topics       │
│  • hold-to-talk mic           │                   │ 3. Save to private knowledge base       │
│  • on-device speech-to-text   │ ─ question text ─▶│    (impressions, time spent, interests) │
│  • speaks the answer          │                   │ 4. Find matching items                  │
│  • draws the answer screen    │ ◀─ answer + UI ── │ 5. CLOUD model (Claude) answers         │
│ Siri / Action Button intent   │                   │    using TEXT ONLY → speech + UI + link │
└───────────────────────────────┘                   └─────────────────────────────────────────┘
```

### What runs where (the hybrid split)
| Step | Runs on | Why there |
|---|---|---|
| Speech to text, text to speech | iPhone | Instant and private |
| Reading screenshots | Local vision model on the laptop | Raw pixels never leave hardware you own |
| Knowledge base | SQLite on the laptop | Your history stays on your machine |
| Answering + designing the screen | Claude in the cloud | Needs strong reasoning; sees only titles, handles, topics and time spent |

### Privacy rules
- Screens the model flags as sensitive (banking, DMs, passwords, health) are dropped.
- Screenshots aren't saved to disk unless debugging is turned on.
- Each answer reports how many text rows and how many images (always 0) went to the cloud.
- Sending screenshots to the cloud is off by default and only happens if we switch it on.

---

## 4. Tools and what each one is for

### iPhone app (Swift)
| Tool | Used for |
|---|---|
| **SwiftUI** | The Lens app's screens |
| **ReplayKit** (Broadcast Upload Extension) | Capturing the screen while you use other apps (the red pill) |
| **Speech** framework | Turning your spoken question into text, on the phone |
| **AVSpeechSynthesizer** | Reading the answer out loud |
| **App Intents** | "Hey Siri, ask Lens" and the Action Button |
| **Swift Charts** | Bar charts in answer screens |
| **App Groups** | Sharing settings between the app and the capture extension |
| **Xcode** + **XcodeGen** | Building the app; XcodeGen generates the Xcode project from `ios/project.yml` |

### Backend (Python, on the laptop)
| Tool | Used for |
|---|---|
| **FastAPI** + **uvicorn** | The web server the phone talks to |
| **uv** | Installing Python and dependencies, running the server and tests |
| **Pillow** | Shrinking screenshots and spotting duplicate screens (perceptual hash) |
| **Ollama** + **qwen2.5vl:7b** | The local vision model that reads screenshots |
| **SQLite** (with FTS5 full-text search) | The private knowledge base |
| **Anthropic Python SDK** + **Claude Opus 5.5** | Answering questions and designing the answer screen (structured output) |
| **ffmpeg** | Demo fallback only: splitting an uploaded screen recording into frames |
| **pytest** | Offline tests |

### Team and infrastructure
| Tool | Used for |
|---|---|
| **Tailscale** | Letting the phone reach the laptop if the venue Wi-Fi blocks it (and keeping the backend off the shared Wi-Fi) |
| **GitHub** | Code, issues, branches and pull requests |
| **Apple Developer account** (paid) | Signing the app and its capture extension to run on a real iPhone |

---

## 5. Tasks

### Done (on `lens-mvp`)
- [x] Screen capture extension that sends a screenshot every 5s
- [x] Backend: duplicate-screen skipping, local vision extraction, knowledge base, interest scores
- [x] Cloud answers with speech + generated screen + open-link action
- [x] iOS app: hold-to-talk, spoken answers, native renderer for the answer screens
- [x] "Hey Siri, ask Lens" intent (works with the Action Button)
- [x] Routing panel showing where each step ran
- [x] Demo fallback: upload a screen recording
- [x] Offline backend tests (6 passing)

### Must do before the 7:00 PM draft
| # | Task | Why | Issue |
|---|---|---|---|
| 1 | Open a pull request for `lens-mvp` and review it | Get the MVP onto `main` | — |
| 2 | Run it end to end on a real iPhone | Nothing is proven until it runs on the phone | #3 |
| 3 | Add a shared token to the backend, or run it only over Tailscale | Right now anyone on the venue Wi-Fi can read the history, spend API credits or wipe the data | — |
| 4 | Fix the "Screens: local model" badge to show the real extractor | It's hard-coded and would be wrong if we switch to cloud vision | — |
| 5 | Test the demo timing: how long until answers reflect what was just captured | The local model takes 12–15s per new screen; a fast scroll creates a backlog | #4 |
| 6 | Time the Siri / Action Button round trip | Siri only waits a limited time for an answer | #8 |
| 7 | Pre-record the fallback screen recording and load it before the demo | Processing it takes minutes, not seconds | #4 |
| 8 | Write the final demo script and rehearse it | | #4 |
| 9 | Update the README with the project and setup | | #1 |
| 10 | Save the project draft on the AGI House page | Finalists are picked from it | #5 |

### Should do if there's time
- Keep screenshots larger before reading them (they're shrunk to ~470px wide, which hurts reading small text on X).
- Make `DELETE /data` also clear frames waiting in the queue.
- Stop the video upload from blocking the server while ffmpeg runs.
- Count the same post once even if the model reads its title slightly differently.

### Stretch: the parts of the original idea Lens doesn't do yet
Our first notes (issue #1) described a **proactive** agent: the screen lights up with a suggestion,
you respond by voice, and it **learns your preferences**. Lens today only answers when asked.
If there's time, in this order:
1. **Proactive suggestion:** after capture, show a suggestion card unprompted ("You've watched 3 videos on AI agents. Want the top creator's latest?"). Issue #11.
2. **Feedback loop:** "not interested" / "more like this" by voice, stored as a preference that changes the next suggestion. Issue #11.
3. **Daily digest notification.**

### Research questions, now answered by the MVP
| Question | Answer used in Lens | Issue |
|---|---|---|
| Can an app read the screen all the time? | On iOS, only through user-started screen broadcasting (ReplayKit) | #7 |
| Ask by voice from the Action Button? | Yes, through an App Intent bound to the Action Button | #8 |
| Replace Siri as the default assistant? | Not on iOS; "Hey Siri, ask Lens" is the workaround | #9 |
| Capture activity from X/Twitter? | Screenshots read by a local vision model, no X API needed | #10 |

These issues can be closed with a short comment pointing here.

---

## 6. Out of scope for today
- Android
- Controlling other apps (Lens only opens links)
- An always-on wake word (iOS doesn't allow it for third-party apps)
- Cloud hosting of the backend; it runs on a laptop for the demo
- App Store release

## 7. Open questions
- **Whose Apple developer account signs the app?** The App Group name must match that account's bundle prefix.
- **Local or cloud vision for the live demo?** Local proves the privacy story but is slow; cloud is faster but sends screenshots out.
- **Which laptop runs the backend during the demo, and on which network?** (Tailscale recommended.)
- **Do we attempt the proactive stretch, or polish the core demo?**

## 8. Setup
See the README on `lens-mvp` for full setup. Short version:
1. **Backend:** install uv and Ollama, `ollama pull qwen2.5vl:7b`, put `ANTHROPIC_API_KEY` in `backend/.env`, run `backend/run.sh`.
2. **iPhone:** install XcodeGen, copy `ios/Config/Local.xcconfig.example` to `Local.xcconfig` with your team ID, bundle prefix and the laptop's IP, run `xcodegen`, open the project in Xcode and run the **Lens** scheme on the phone.
