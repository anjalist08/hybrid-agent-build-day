import OpenUI
import SwiftUI

/// The component library the agent writes against: OpenUI's chat library plus Lens components.
/// Keep the SeatMap schema in sync with tools/openui-prompt/Sources/LensPrompt/main.swift,
/// which generates the agent's system prompt from the same definition.
enum LensComponents {
    static let seatMapSchema = ComponentSchema(
        "SeatMap",
        description: "Interactive seat map of a venue. Tap free seats to select them; held and booked seats are greyed out. "
            + "Pass the whole get_seats Query result as `seats`, bind `selected` to a $variable holding the chosen seat ids "
            + "(string[]), and cap the selection with maxSeats.",
        props: [
            .required("seats", .any),
            .binding("selected", .array(.string)),
            .optional("maxSeats", .number),
        ]
    )

    @MainActor static let library: ComponentLibrary = ComponentLibrary.openUIChat.addingContent(
        [ComponentDefinition(seatMapSchema) { context in SeatMapComponent(context: context) }],
        group: "Ticketing"
    )
}

/// Calls the backend for every Query()/Mutation() in a generated UI (POST /tools/{name}).
struct LensToolProvider: OpenUIToolProvider {
    struct ToolFailure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    func callTool(_ name: String, arguments: OpenUIObject) async throws -> OpenUIValue {
        var request = URLRequest(url: SharedConfig.backendURL.appendingPathComponent("tools/\(name)"))
        request.httpMethod = "POST"
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data(OpenUIJSON.stringify(OpenUIValue.object(arguments).plainJSON).utf8)
        let (data, response) = try await URLSession.shared.data(for: request)
        let value = try OpenUIJSON.parse(data)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw ToolFailure(message: value["error"]?.stringValue ?? "Request failed (\(http.statusCode))")
        }
        return value
    }
}
