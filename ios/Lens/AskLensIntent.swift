import AppIntents
import SwiftUI

/// "Hey Siri, ask Lens" works while another app (X, YouTube...) stays on screen.
/// Siri asks for the question, Lens answers out loud and shows the generated UI as a snippet.
/// Also assignable to the Action Button via Shortcuts.
struct AskLensIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Lens"
    static var description = IntentDescription("Ask about what you've been reading and watching.")

    @Parameter(title: "Question", requestValueDialog: "What do you want to know?")
    var question: String

    func perform() async throws -> some IntentResult & ProvidesDialog & ShowsSnippetView {
        let response = try await LensAPI.query(question, source: "siri")
        return .result(dialog: "\(response.answer.speech)") {
            GenScreenView(screen: response.answer.ui)
                .padding()
        }
    }
}

struct LensShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AskLensIntent(),
            phrases: [
                "Ask \(.applicationName)",
                "Ask \(.applicationName) a question",
                "What have I been watching on \(.applicationName)",
            ],
            shortTitle: "Ask Lens",
            systemImageName: "eye"
        )
    }
}
