import SwiftUI

/// What Lens noticed on this device that might be worth acting on.
struct Suggestion: Identifiable, Equatable {
    enum Kind: Equatable {
        case trip(title: String, seed: String)
        case ask(question: String)
    }

    let id: String
    let category: String
    let time: String
    let text: String
    let action: String
    let kind: Kind
}

/// A shared chat Lens can act on. In the demo it's the "Ski squad" group chat.
enum DemoContent {
    static let skiSquad = """
    Group chat "Ski squad ⛷️"
    Alex: ok we're actually doing Tahoe this time 😤
    Sam: MLK weekend? I can do Fri Jan 15 – Mon Jan 18
    Alex: yes!! Palisades. I want a place near the lifts
    Sam: we'll need a car from Reno, I'm not driving 4 hrs from SF
    Alex: someone book it before we chicken out 😂
    """
}

/// Navigation targets from Home.
enum Route: Hashable {
    case chat(title: String?, seed: String?)
}

struct HomeView: View {
    @State private var path: [Route] = []
    @State private var dismissed: Set<String> = []
    @State private var memoryLine: String?
    @State private var showSettings = false
    @State private var showPermission: Suggestion?
    @State private var showMemory = false
    @State private var showSeatMapPreview = false

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(spacing: 12) {
                        clock.padding(.top, 24).padding(.bottom, 28)
                        ForEach(visibleSuggestions) { item in
                            SuggestionRow(item: item, onAction: { act(on: item) }, onDismiss: {
                                withAnimation { _ = dismissed.insert(item.id) }
                            })
                        }
                    }
                    .padding(.horizontal, 20)
                }
                bottomBar
            }
            .background(LensWallpaper().ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: Route.self) { route in
                switch route {
                case let .chat(title, seed):
                    AgentChatView(title: title, seed: seed) { path.removeAll() }
                        .toolbar(.hidden, for: .navigationBar)
                }
            }
        }
        .tint(LensDesign.blue)
        .preferredColorScheme(.light)
        .sheet(isPresented: $showSettings) { AppAccessView() }
        .sheet(isPresented: $showMemory) { AssistantChatView() }
        #if DEBUG
        .sheet(isPresented: $showSeatMapPreview) { SeatMapPreview() }
        #endif
        .fullScreenCover(item: $showPermission) { item in
            PermissionView(
                onAllow: {
                    AccessSettings.set(.sharedChats, true)
                    showPermission = nil
                    open(item)
                },
                onContinueWithout: {
                    showPermission = nil
                    path.append(.chat(title: title(of: item), seed: nil))
                },
                onBack: { showPermission = nil }
            )
        }
        .task { await loadMemoryLine() }
        #if DEBUG
        .task {
            // Simulator screenshots: `--preview-trip` opens the trip chat as if "Take a look" was tapped.
            if ProcessInfo.processInfo.arguments.contains("--preview-trip") {
                path = [.chat(title: "Tahoe trip", seed: DemoContent.skiSquad)]
            }
            if ProcessInfo.processInfo.arguments.contains("--preview-settings") { showSettings = true }
            if ProcessInfo.processInfo.arguments.contains("--preview-seatmap") { showSeatMapPreview = true }
            if ProcessInfo.processInfo.arguments.contains("--preview-permission") { showPermission = suggestions[0] }
        }
        #endif
    }

    // MARK: Pieces

    private var clock: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            VStack(spacing: 4) {
                Text(context.date.formatted(.dateTime.weekday(.wide).month(.wide).day()))
                    .font(.title3.weight(.medium)).foregroundStyle(.white.opacity(0.85))
                Text(Self.clockFormat.string(from: context.date))
                    .font(.system(size: 96, weight: .thin))
                    .foregroundStyle(.white)
                    .monospacedDigit()
                    .shadow(color: .black.opacity(0.12), radius: 8, y: 2)
                Text(greeting(for: context.date)).font(.body).foregroundStyle(.white.opacity(0.85))
            }
        }
    }

    private static let clockFormat: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm"
        return f
    }()

    private var bottomBar: some View {
        HStack {
            Button("Settings") { showSettings = true }
                .font(.body.weight(.medium)).foregroundStyle(.white)
            Spacer()
            Button {
                path.append(.chat(title: nil, seed: nil))
            } label: {
                Text("Ask").font(.body.weight(.medium)).foregroundStyle(LensDesign.blue)
                    .padding(.horizontal, 30).frame(height: 38)
                    .background(.white, in: Capsule())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 28)
        .padding(.vertical, 12)
    }

    // MARK: Suggestions

    private var suggestions: [Suggestion] {
        [
            Suggestion(id: "trip", category: "Ski squad", time: "now",
                       text: "Alex and Sam are planning Tahoe for MLK weekend. Want me to put the trip together?",
                       action: "Take a look", kind: .trip(title: "Tahoe trip", seed: DemoContent.skiSquad)),
            Suggestion(id: "memory", category: "From your screen", time: "today",
                       text: memoryLine ?? "Lens remembers what you read and watch — on this device. Ask what you saw earlier.",
                       action: "Ask about it", kind: .ask(question: "What have I been looking at recently?")),
        ]
    }

    private var visibleSuggestions: [Suggestion] { suggestions.filter { !dismissed.contains($0.id) } }

    private func act(on item: Suggestion) {
        switch item.kind {
        case .trip:
            if AccessSettings.isOn(.sharedChats) { open(item) } else { showPermission = item }
        case let .ask(question):
            path.append(.chat(title: nil, seed: question))
        }
    }

    private func open(_ item: Suggestion) {
        if case let .trip(title, seed) = item.kind { path.append(.chat(title: title, seed: seed)) }
    }

    private func title(of item: Suggestion) -> String? {
        if case let .trip(title, _) = item.kind { return title }
        return nil
    }

    private func greeting(for date: Date) -> String {
        switch Calendar.current.component(.hour, from: date) {
        case 5..<12: return "Good morning"
        case 12..<17: return "Good afternoon"
        default: return "Good evening"
        }
    }

    /// One line from the local knowledge base: the top topic and time spent.
    private func loadMemoryLine() async {
        struct Interest: Decodable { let name: String; let dwellS: Double; let impressions: Int }
        var request = URLRequest(url: SharedConfig.backendURL.appendingPathComponent("interests"))
        request.url?.append(queryItems: [URLQueryItem(name: "type", value: "topic"), URLQueryItem(name: "limit", value: "1")])
        request.timeoutInterval = 4
        guard let (data, _) = try? await URLSession.shared.data(for: request) else { return }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let top = try? decoder.decode([Interest].self, from: data).first, top.dwellS > 0 else { return }
        let minutes = max(1, Int(top.dwellS / 60))
        memoryLine = "You spent \(minutes) min on \(top.impressions) things about \(top.name). Want a quick recap?"
    }
}

private struct SuggestionRow: View {
    let item: Suggestion
    let onAction: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(item.category).font(.subheadline).foregroundStyle(LensDesign.muted)
                Spacer()
                Text(item.time).font(.footnote).foregroundStyle(LensDesign.muted)
            }
            Text(item.text).font(.body).foregroundStyle(LensDesign.ink).fixedSize(horizontal: false, vertical: true)
            HStack {
                Button(item.action, action: onAction).font(.subheadline.weight(.medium)).foregroundStyle(LensDesign.blue)
                Spacer()
                Button("Not now", action: onDismiss).font(.subheadline).foregroundStyle(LensDesign.muted)
            }
            .buttonStyle(.plain)
        }
        .padding(18)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: LensDesign.bubbleRadius, style: .continuous))
    }
}
