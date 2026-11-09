import ReplayKit
import SwiftUI

@main
struct LensApp: App {
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            HomeView()
                // Heartbeat while Lens is in front: the capture extension skips frames until it expires,
                // so screen memory never records Lens itself. Expires on its own if the app is killed.
                .task {
                    while !Task.isCancelled {
                        if scenePhase == .active { LensForeground.mark() }
                        try? await Task.sleep(for: .seconds(2))
                    }
                }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { LensForeground.mark() } else { LensForeground.clear() }
        }
    }
}

enum LensForeground {
    static func mark() {
        SharedConfig.defaults.set(Date().timeIntervalSince1970 + 4, forKey: SharedConfig.Keys.lensForegroundUntil)
    }

    static func clear() {
        SharedConfig.defaults.set(0, forKey: SharedConfig.Keys.lensForegroundUntil)
    }
}

/// Holds the current question/answer and talks to the backend.
@MainActor
final class AppModel: ObservableObject {
    @Published var answer: LensAnswer?
    @Published var route: RouteInfo?
    @Published var lastQuestion = ""
    @Published var isThinking = false
    @Published var error: String?
    @Published var health: Health?
    @Published var broadcasting = false
    @Published var framesSent = 0
    @Published var uploadError: String?

    func ask(_ text: String, source: String, voice: VoiceController) async {
        let question = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !question.isEmpty else { return }
        lastQuestion = question
        isThinking = true
        error = nil
        defer { isThinking = false }
        do {
            let response = try await LensAPI.query(question, source: source)
            answer = response.answer
            route = response.route
            voice.speak(response.answer.speech)
            if response.answer.action.kind == "open_url",
               let s = response.answer.action.url, let url = URL(string: s) {
                // Let the spoken answer start before switching apps.
                try? await Task.sleep(for: .seconds(1.5))
                await UIApplication.shared.open(url)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Polls backend health and the extension's shared counters for the status bar.
    func refreshStatus() async {
        let d = SharedConfig.defaults
        broadcasting = d.bool(forKey: SharedConfig.Keys.broadcasting)
        framesSent = d.integer(forKey: SharedConfig.Keys.framesSent)
        uploadError = d.string(forKey: SharedConfig.Keys.lastUploadError)
        health = try? await LensAPI.health()
    }
}

/// System sheet that starts/stops the Broadcast Upload Extension (the red recording pill).
struct BroadcastPickerButton: UIViewRepresentable {
    func makeUIView(context: Context) -> RPSystemBroadcastPickerView {
        let picker = RPSystemBroadcastPickerView(frame: CGRect(x: 0, y: 0, width: 44, height: 44))
        picker.preferredExtension = (Bundle.main.bundleIdentifier ?? "") + ".broadcast"
        picker.showsMicrophoneButton = false
        return picker
    }

    func updateUIView(_ uiView: RPSystemBroadcastPickerView, context: Context) {}
}
