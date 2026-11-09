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

    /// A pasted group chat or email (several lines) is shown as a shared-conversation card.
    var isSharedConversation: Bool { role == .user && display.split(separator: "\n").count >= 3 }
}

extension Notification.Name {
    /// Posted by LensToolProvider when the generated UI runs a tool (object: tool name).
    static let lensToolCalled = Notification.Name("lensToolCalled")
}

@MainActor
@Observable
final class AgentStore {
    static let steps = ["Plan", "Flights & stays", "Book", "Share"]

    var turns: [AgentTurn] = []
    var isBusy = false
    /// Index into `steps`, advanced by what the user does in the generated UI.
    var step = 0
    private var task: Task<Void, Never>?
    @ObservationIgnored private var observer: NSObjectProtocol?

    init() {
        observer = NotificationCenter.default.addObserver(forName: .lensToolCalled, object: nil, queue: .main) { [weak self] note in
            let tool = note.object as? String ?? ""
            MainActor.assumeIsolated { self?.advance(for: tool) }
        }
    }

    private func advance(for tool: String) {
        let target: Int
        switch tool {
        case "search_flights", "search_stays", "search_cars": target = 1
        case "book_trip": target = 2
        case "notify_friends": target = 3
        default: return
        }
        step = max(step, target)
    }

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
        let isSharedChat = text.split(separator: "\n").count >= 3
        reply.status = isSharedChat ? "Reading the chat on this device…" : turns.count <= 2 ? "Checking your memory…" : "Working on it…"
        task = Task { [weak self] in
            await self?.stream(history: Array(history), into: reply)
        }
    }

    func reset() {
        task?.cancel()
        turns.removeAll()
        isBusy = false
        step = 0
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
        request.timeoutInterval = 300
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["messages": history])
        do {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            if let http = response as? HTTPURLResponse, http.statusCode != 200 {
                reply.error = "Lens server error \(http.statusCode)"
                return
            }
            for try await line in bytes.lines where line.hasPrefix("data: ") {
                guard let data = line.dropFirst(6).data(using: .utf8),
                      let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let type = event["type"] as? String else { continue }
                switch type {
                case "status":
                    switch event["status"] as? String {
                    case "thinking": reply.status = "Thinking it through…"
                    case "tool":
                        reply.status = (event["tool"] as? String) == "research_topic"
                            ? "Researching people and companies on the web… (about a minute)"
                            : "Looking through what you've seen…"
                    default: reply.status = "Putting it together…"
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

/// Chat with the agent: "‹ Home · Title", step tracker, bubbles and OpenUI cards, composer.
struct AgentChatView: View {
    let title: String?
    /// A shared conversation to start from (sent once, when the user opened it from Home).
    let seed: String?
    let onHome: () -> Void

    @State private var store = AgentStore()
    @State private var draft = ""
    @State private var seeded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        AssistantBubble { Text(title == nil ? "What can I help you with today?" : "I'll read the chat here on your phone and pull out the plan.") }
                        ForEach(store.turns) { turn in
                            TurnView(turn: turn).id(turn.id)
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 20)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: store.turns.count) {
                    if let last = store.turns.last { withAnimation { proxy.scrollTo(last.id, anchor: .top) } }
                }
                #if DEBUG
                .task { await debugScroll(proxy) }
                #endif
            }
            Composer(text: $draft, disabled: store.isBusy) {
                let text = draft
                draft = ""
                store.send(display: text)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 8)
        }
        .background(Color.white)
        .environment(\.openUITheme, LensDesign.openUITheme)
        .task {
            guard !seeded else { return }
            seeded = true
            if let seed { store.send(display: seed) }
            #if DEBUG
            await debugAutoconfirm()
            #endif
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 18) {
            Breadcrumb(title: title, onBack: onHome)
            // Trip steps only for trip conversations (opened from a shared chat, or once a search ran).
            if title != nil || store.step > 0 {
                StepTracker(steps: AgentStore.steps, current: store.step)
            }
        }
        .padding(.horizontal, 24)
        .padding(.top, 8)
        .padding(.bottom, 4)
    }

    #if DEBUG
    /// `--agent-autoconfirm` taps "Looks good" once the plan has streamed (simulator screenshots).
    private func debugAutoconfirm() async {
        guard ProcessInfo.processInfo.arguments.contains("--agent-autoconfirm"), seed != nil else { return }
        try? await Task.sleep(for: .seconds(2))
        while store.isBusy { try? await Task.sleep(for: .milliseconds(300)) }
        store.send(display: "Looks good — find flights, stays & cars", content: "Confirm the plan and find options")
    }

    /// `--agent-scroll <fraction>` scrolls to the last turn after the answer streams.
    private func debugScroll(_ proxy: ScrollViewProxy) async {
        let args = ProcessInfo.processInfo.arguments
        guard let i = args.firstIndex(of: "--agent-scroll"), i + 1 < args.count, let y = Double(args[i + 1]) else { return }
        try? await Task.sleep(for: .seconds(args.contains("--agent-autoconfirm") ? 34 : 18))
        withAnimation { proxy.scrollTo(store.turns.last?.id, anchor: UnitPoint(x: 0.5, y: y)) }
    }
    #endif
}

private struct TurnView: View {
    let turn: AgentTurn

    var body: some View {
        switch turn.role {
        case .user:
            if turn.isSharedConversation {
                SharedConversationCard(text: turn.display)
            } else {
                UserBubble(text: turn.display)
            }
        case .assistant:
            VStack(alignment: .leading, spacing: 12) {
                if turn.isStreaming && turn.program.isEmpty {
                    AssistantBubble {
                        HStack(spacing: 10) {
                            ProgressView()
                            Text(turn.status).foregroundStyle(LensDesign.muted)
                        }
                    }
                }
                if let runtime = turn.runtime, !turn.program.isEmpty {
                    OpenUIView(runtime: runtime)
                }
                if let error = turn.error {
                    AssistantBubble { Text(error).foregroundStyle(.red) }
                }
            }
        }
    }
}

/// A pasted group chat / email: shown as what it is, with where it stays.
private struct SharedConversationCard: View {
    let text: String
    @State private var expanded = false

    private var lines: [Substring] { text.split(separator: "\n") }
    private var heading: String { String(lines.first ?? "Shared conversation") }
    private var bodyText: String { lines.dropFirst().joined(separator: "\n") }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(heading).font(.headline).foregroundStyle(.white)
            Text("Shared with Lens · stays on this device").font(.footnote).foregroundStyle(.white.opacity(0.6))
            Text(bodyText)
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.92))
                .lineLimit(expanded ? nil : 4)
            Button(expanded ? "Show less" : "Show all") { withAnimation { expanded.toggle() } }
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.white.opacity(0.8))
        }
        .padding(16)
        .background(LensDesign.ink, in: RoundedRectangle(cornerRadius: LensDesign.bubbleRadius, style: .continuous))
        .frame(maxWidth: 320, alignment: .trailing)
        .frame(maxWidth: .infinity, alignment: .trailing)
    }
}
