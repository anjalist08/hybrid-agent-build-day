import OpenUI
import SwiftUI

/// One message in the agent chat. Assistant turns own an OpenUI runtime that renders the
/// streamed OpenUI Lang program and keeps its state ($selected seats, form fields, mutations).
@MainActor
@Observable
final class AgentTurn: Identifiable {
    enum Role { case user, assistant }

    let id = UUID()
    let role: Role
    /// What the user sees for their own turn.
    let display: String
    /// What the model receives (for actions: the OpenUI envelope with clicked item and form state).
    let content: String
    var program = ""
    var status = ""
    var error: String?
    var isStreaming = false
    let runtime: OpenUIRuntime?

    init(role: Role, display: String, content: String, runtime: OpenUIRuntime? = nil) {
        self.role = role
        self.display = display
        self.content = content
        self.runtime = runtime
    }
}

@MainActor
@Observable
final class AgentStore {
    var turns: [AgentTurn] = []
    var isBusy = false
    private var task: Task<Void, Never>?

    func send(display: String, content: String? = nil) {
        let text = display.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isBusy else { return }
        turns.append(AgentTurn(role: .user, display: text, content: content ?? text))

        let runtime = OpenUIRuntime(library: LensComponents.library, toolProvider: LensToolProvider())
        let reply = AgentTurn(role: .assistant, display: "", content: "", runtime: runtime)
        runtime.onAction = { [weak self] event in self?.handle(event) }
        turns.append(reply)

        let history = turns.dropLast().map { turn -> [String: String] in
            turn.role == .user ? ["role": "user", "content": turn.content] : ["role": "assistant", "content": turn.program]
        }.filter { !($0["content"] ?? "").isEmpty }

        isBusy = true
        reply.isStreaming = true
        reply.status = "Reading the conversation…"
        task = Task { [weak self] in
            await self?.stream(history: Array(history), into: reply)
        }
    }

    func reset() {
        task?.cancel()
        turns.removeAll()
        isBusy = false
    }

    private func handle(_ event: ActionEvent) {
        if event.isOpenURL, let url = event.url {
            UIApplication.shared.open(url)
        } else if event.isContinueConversation {
            send(display: event.humanFriendlyMessage, content: event.assistantMessage)
        }
    }

    private func stream(history: [[String: String]], into reply: AgentTurn) async {
        defer {
            reply.isStreaming = false
            reply.runtime?.update(response: reply.program.isEmpty ? nil : reply.program, isStreaming: false)
            isBusy = false
        }
        var request = URLRequest(url: SharedConfig.backendURL.appendingPathComponent("agent/chat"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["messages": history])
        do {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            if let http = response as? HTTPURLResponse, http.statusCode != 200 {
                reply.error = "Backend error \(http.statusCode)"
                return
            }
            for try await line in bytes.lines where line.hasPrefix("data: ") {
                guard let data = line.dropFirst(6).data(using: .utf8),
                      let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let type = event["type"] as? String else { continue }
                switch type {
                case "status":
                    switch event["status"] as? String {
                    case "thinking": reply.status = "Thinking…"
                    case "tool": reply.status = "Looking things up…"
                    default: reply.status = "Putting your trip together…"
                    }
                case "delta":
                    reply.program += event["text"] as? String ?? ""
                    reply.runtime?.update(response: reply.program, isStreaming: true)
                case "reset":
                    reply.program = ""
                    reply.runtime?.update(response: nil, isStreaming: true)
                case "error":
                    reply.error = event["message"] as? String ?? "Something went wrong."
                default:
                    break
                }
            }
        } catch is CancellationError {
        } catch {
            reply.error = error.localizedDescription
        }
    }
}

struct AgentChatView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var store = AgentStore()
    @State private var draft = ""
    @FocusState private var inputFocused: Bool

    /// Demo inputs: trips friends plan ad hoc over group chats and email.
    private let samples = [
        """
        Group chat "Ski squad ⛷️"
        Alex: ok we're actually doing Tahoe this time 😤
        Sam: MLK weekend? I can do Fri Jan 15 – Mon Jan 18
        Alex: yes!! Palisades. I want a place near the lifts
        Sam: we'll need a car from Reno, I'm not driving 4 hrs from SF
        Alex: someone book it before we chicken out 😂
        """,
        """
        Email from Priya — Subject: Austin for my birthday?!
        Hey! Thinking Austin Mar 5–8 for my 30th. Me, you and Jordan flying from SF.         Somewhere walkable near South Congress, and a car for a day trip to Hill Country wineries. You in?
        """,
    ]

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        if store.turns.isEmpty { emptyState }
                        ForEach(store.turns) { turn in
                            TurnView(turn: turn).id(turn.id)
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .padding()
                }
                #if DEBUG
                .task {
                    // Simulator screenshots: `--agent-scroll <fraction>` scrolls down after the answer streams.
                    let args = ProcessInfo.processInfo.arguments
                    if let i = args.firstIndex(of: "--agent-scroll"), i + 1 < args.count, let y = Double(args[i + 1]) {
                        try? await Task.sleep(for: .seconds(22))
                        withAnimation { proxy.scrollTo(store.turns.last?.id, anchor: UnitPoint(x: 0.5, y: y)) }
                    }
                }
                #endif
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: store.turns.count) {
                    if let last = store.turns.last { withAnimation { proxy.scrollTo(last.id, anchor: .top) } }
                }
            }
            .safeAreaInset(edge: .bottom) { inputBar }
            #if DEBUG
            .task {
                // Simulator screenshots: `--agent-autosend` sends the first sample message.
                let args = ProcessInfo.processInfo.arguments
                if args.contains("--agent-autosend"), store.turns.isEmpty {
                    store.send(display: samples[0])
                    // `--agent-autoconfirm` also taps "Looks good" once the plan has streamed.
                    if args.contains("--agent-autoconfirm") {
                        try? await Task.sleep(for: .seconds(2))
                        while store.isBusy { try? await Task.sleep(for: .milliseconds(300)) }
                        store.send(display: "Looks good — find flights, stays & cars",
                                   content: "Confirm the plan and find options")
                    }
                }
            }
            #endif
            .navigationTitle("Lens Agent")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { store.reset() } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("New chat")
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Planning a trip with friends?").font(.title2.bold())
            Text("Paste the group chat or email. Lens pieces together the plan, then books flights with seats, a stay and a car — and lets your friends know.")
                .foregroundStyle(.secondary)
            ForEach(samples, id: \.self) { sample in
                Button { store.send(display: sample) } label: {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: sample.hasPrefix("Email") ? "envelope.fill" : "message.fill")
                            .foregroundStyle(sample.hasPrefix("Email") ? .blue : .green)
                        Text(sample).font(.subheadline).multilineTextAlignment(.leading).foregroundStyle(.primary)
                        Spacer(minLength: 0)
                    }
                    .padding(12)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var inputBar: some View {
        HStack(spacing: 10) {
            Button {
                if let text = UIPasteboard.general.string { store.send(display: text) }
            } label: {
                Image(systemName: "doc.on.clipboard").font(.title3)
            }
            .accessibilityLabel("Paste from clipboard")
            .disabled(store.isBusy)

            TextField("Paste a group chat or email…", text: $draft, axis: .vertical)
                .lineLimit(1...4)
                .textFieldStyle(.roundedBorder)
                .focused($inputFocused)
                .submitLabel(.send)
                .onSubmit(sendDraft)

            Button(action: sendDraft) {
                Image(systemName: "arrow.up.circle.fill").font(.title)
            }
            .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty || store.isBusy)
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(.bar)
    }

    private func sendDraft() {
        let text = draft
        draft = ""
        inputFocused = false
        store.send(display: text)
    }
}

private struct TurnView: View {
    let turn: AgentTurn

    var body: some View {
        switch turn.role {
        case .user:
            HStack {
                Spacer(minLength: 40)
                Text(turn.display)
                    .padding(12)
                    .background(Color.accentColor.opacity(0.15), in: RoundedRectangle(cornerRadius: 16))
            }
        case .assistant:
            VStack(alignment: .leading, spacing: 8) {
                if turn.isStreaming && turn.program.isEmpty {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text(turn.status).font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                if let runtime = turn.runtime, !turn.program.isEmpty {
                    OpenUIView(runtime: runtime)
                }
                if let error = turn.error {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .font(.footnote).foregroundStyle(.red)
                }
            }
        }
    }
}
