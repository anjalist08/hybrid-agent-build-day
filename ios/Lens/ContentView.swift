import SwiftUI

struct ContentView: View {
    @State private var concertPlan: ConcertDemoPlan?
    @State private var showAssistant = false
    @State private var showSettings = false
    @State private var showRoutes = false
    @State private var showTickets = false

    var body: some View {
        NavigationStack {
            RecommendationHomeView(plan: concertPlan) {
                showConcert = true
            }
            .navigationDestination(isPresented: $showConcert) {
                ConcertDetailView { showTickets = true }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showRoutes = true } label: {
                        Image(systemName: "point.3.connected.trianglepath.dotted")
                    }
                    .accessibilityLabel("Where it ran")
                }
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { showAssistant = true } label: { Image(systemName: "waveform") }
                        .accessibilityLabel("Ask Lens")
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Settings")
                }
            }
            .sheet(isPresented: $showAssistant) { AssistantChatView() }

            .sheet(isPresented: $showSettings) { SettingsView() }
            .sheet(isPresented: $showRoutes) { RoutingView() }
            .sheet(isPresented: $showTickets, onDismiss: {
                if concertPlan != nil { showConcert = false }
            }) {
                TicketFlowView { concertPlan = $0 }
            }
        }
        .tint(.primary)
        .preferredColorScheme(.light)
        #if DEBUG
        .task {
            // Deterministic entry points for simulator screenshots; no external actions.
            let arguments = ProcessInfo.processInfo.arguments
            showConcert = arguments.contains("--preview-concert")
            showTickets = arguments.contains("--preview-tickets")

        }
        #endif
    }

    @State private var showConcert = false
}

struct AssistantChatView: View {
    @StateObject private var model = AppModel()
    @StateObject private var voice = VoiceController()
    @State private var typed = ""
    @State private var showRoutes = false
    @State private var showSettings = false

    private let statusTimer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                captureBar
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        conversation
                        if let answer = model.answer {
                            GenScreenView(screen: answer.ui)
                        } else if !model.isThinking {
                            emptyState
                        }
                    }
                    .padding()
                }
                inputBar
            }
            .navigationTitle("Lens")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showRoutes = true } label: { Image(systemName: "point.3.connected.trianglepath.dotted") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                }
            }
            .sheet(isPresented: $showRoutes) { RoutingView() }
            .sheet(isPresented: $showSettings) { SettingsView() }
        }
        .task {
            await voice.requestPermissions()
            await model.refreshStatus()
        }
        .onReceive(statusTimer) { _ in Task { await model.refreshStatus() } }
    }

    // MARK: - Sections

    private var captureBar: some View {
        HStack(spacing: 10) {
            BroadcastPickerButton()
                .frame(width: 36, height: 36)
                .background(Color.red.opacity(model.broadcasting ? 0.2 : 0.08), in: Circle())
            VStack(alignment: .leading, spacing: 1) {
                Text(captureTitle)
                    .font(.subheadline.weight(.semibold))
                Group {
                    if let err = model.uploadError {
                        Text("Upload error: \(err)").foregroundStyle(.red)
                    } else if let h = model.health {
                        Text("\(model.framesSent) sent · \(h.processed) read · \(h.deduped) same-screen · \(h.queue) queued")
                    } else {
                        Text("Backend unreachable: \(SharedConfig.backendURL.absoluteString)").foregroundStyle(.orange)
                    }
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private var captureTitle: String {
        #if targetEnvironment(simulator)
        return "Screen capture needs a real iPhone (use /ingest/video)"
        #else
        return model.broadcasting ? "Capturing screen" : "Tap ● to start screen capture"
        #endif
    }

    @ViewBuilder
    private var conversation: some View {
        if voice.isListening {
            Text(voice.transcript.isEmpty ? "Listening…" : voice.transcript)
                .font(.title3)
                .foregroundStyle(.secondary)
        } else if !model.lastQuestion.isEmpty {
            Text("“\(model.lastQuestion)”").font(.title3.weight(.medium))
        }
        if model.isThinking {
            HStack { ProgressView(); Text("Thinking…").foregroundStyle(.secondary) }
        }
        if let error = model.error ?? voice.permissionError {
            Text(error).font(.footnote).foregroundStyle(.red)
        }
        if let answer = model.answer, !model.isThinking {
            Text(answer.speech).font(.body)
            if let route = model.route { RouteBadges(route: route, sttOnDevice: voice.onDevice) }
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Hold the mic and ask, for example:").font(.subheadline).foregroundStyle(.secondary)
            ForEach(["What have I been watching about AI agents?",
                     "Who do I read the most on X?",
                     "How much time did I spend on YouTube today?",
                     "Open the last video I watched"], id: \.self) { s in
                Button(s) { Task { await model.ask(s, source: "typed", voice: voice) } }
                    .font(.subheadline)
            }
        }
    }

    private var inputBar: some View {
        HStack(spacing: 12) {
            TextField("Ask about what you've seen…", text: $typed)
                .textFieldStyle(.roundedBorder)
                .submitLabel(.send)
                .onSubmit {
                    let q = typed
                    typed = ""
                    Task { await model.ask(q, source: "typed", voice: voice) }
                }
            micButton
        }
        .padding()
        .background(.bar)
    }

    /// Hold to talk, release to send.
    private var micButton: some View {
        Image(systemName: voice.isListening ? "waveform" : "mic.fill")
            .font(.title2)
            .foregroundStyle(.white)
            .frame(width: 60, height: 60)
            .background(voice.isListening ? Color.red : Color.accentColor, in: Circle())
            .scaleEffect(voice.isListening ? 1.12 : 1)
            .animation(.spring(duration: 0.2), value: voice.isListening)
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in if !voice.isListening { voice.startListening() } }
                    .onEnded { _ in
                        Task {
                            let text = await voice.stopListening()
                            await model.ask(text, source: voice.onDevice ? "device-stt" : "apple-stt", voice: voice)
                        }
                    }
            )
            .accessibilityLabel("Hold to ask")
    }
}

/// Where each step of the last answer ran: the "hybrid" story in one row.
struct RouteBadges: View {
    let route: RouteInfo
    let sttOnDevice: Bool

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                badge("Speech", sttOnDevice ? "on-device" : "Apple", .green)
                badge("Screens", "local model", .green)
                badge("Answer", "\(route.model) · \(String(format: "%.1fs", Double(route.ms) / 1000))", .blue)
                badge("Sent to cloud", "\(route.impressionsSent ?? 0) text rows, \(route.imagesSent ?? 0) images", .orange)
            }
        }
    }

    private func badge(_ label: String, _ value: String, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Text(label).fontWeight(.semibold)
            Text(value)
        }
        .font(.caption2)
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(color.opacity(0.15), in: Capsule())
    }
}

struct RoutingView: View {
    @State private var entries: [RouteLogEntry] = []
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let error { Text(error).foregroundStyle(.red) }
                ForEach(entries) { e in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack {
                            Text(e.op).font(.subheadline.weight(.semibold))
                            Text(e.location.uppercased())
                                .font(.caption2.weight(.bold))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background((e.location == "cloud" ? Color.blue : Color.green).opacity(0.2), in: Capsule())
                            Spacer()
                            if let ms = e.ms { Text("\(ms) ms").font(.caption).monospacedDigit() }
                            Image(systemName: e.ok == 1 ? "checkmark.circle.fill" : "xmark.octagon.fill")
                                .foregroundStyle(e.ok == 1 ? .green : .red)
                        }
                        Text([e.model, e.detail].compactMap { $0 }.joined(separator: " · "))
                            .font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    }
                }
            }
            .navigationTitle("Where it ran")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private func load() async {
        do { entries = try await LensAPI.routes(); error = nil } catch { self.error = error.localizedDescription }
    }
}

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var url = SharedConfig.backendURL.absoluteString
    @State private var interval = SharedConfig.captureInterval

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    TextField("http://100.64.0.2:8000", text: $url)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Section {
                    Stepper("Every \(Int(interval)) s", value: $interval, in: 2...30, step: 1)
                } header: {
                    Text("Screenshot cadence")
                } footer: {
                    Text("Takes effect the next time you start screen capture.")
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        SharedConfig.setBackendURL(url)
                        SharedConfig.captureInterval = interval
                        dismiss()
                    }
                }
            }
        }
    }
}
