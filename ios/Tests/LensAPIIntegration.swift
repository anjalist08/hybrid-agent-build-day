import Foundation

// Isolated from app preferences: all requests go to the temporary fixture backend.
enum SharedConfig {
    static let backendURL = URL(string: ProcessInfo.processInfo.environment["LENS_TEST_URL"]!)!
}

@main
struct LensAPIIntegration {
    static func main() async throws {
        let health = try await LensAPI.health()
        precondition(health.ok)
        let interests = try await LensAPI.interests()
        precondition(interests.count == 1 && interests[0].name == "ai agents")
        precondition(interests[0].type == "topic" && interests[0].dwellS > 0)
        let history = try await LensAPI.impressions()
        precondition(history.count == 1 && history[0].title == "Integration fixture: AI agents")
        precondition(history[0].author == "Fixture creator" && history[0].tsEnd > 0)
        let response = try await LensAPI.query("What did I watch?", source: "suggestion")
        precondition(response.answer.ui.components.first?.type == "card")
        precondition(response.route.transcriptSource == "suggestion")
        precondition(response.route.imagesSent == 0 && response.answer.action.kind == "none")
        do {
            _ = try await LensAPI.query("   ", source: "typed")
            fatalError("Expected HTTP 400 for an empty query")
        } catch LensAPIError.server(let status, _) {
            precondition(status == 400)
        }
        do {
            _ = try await LensAPI.health(baseURL: URL(string: "file:///tmp/not-a-backend")!)
            fatalError("Expected URL validation failure")
        } catch LensAPIError.invalidURL { }
        print("PASS: Swift API → FastAPI health, interests, history, query, HTTP error and URL validation")
    }
}
