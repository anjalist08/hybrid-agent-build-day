import MessageUI
import OpenUI
import SwiftUI

/// The component library the agent writes against: OpenUI's chat library plus Lens's trip components.
/// Keep the schemas in sync with tools/openui-prompt/Sources/LensPrompt/main.swift, which generates
/// the agent's system prompt from the same definitions.
enum LensComponents {
    static let offerPickerSchema = ComponentSchema(
        "OfferPicker",
        description: "Native list of bookable options (flights, stays or cars) with prices; the user taps one. "
            + "Pass the whole search_flights / search_stays / search_cars Query result as `options`, and bind `selected` "
            + "to a $variable that receives the chosen option id.",
        props: [
            .required("options", .any),
            .binding("selected", .string),
        ]
    )

    static let cabinSeatMapSchema = ComponentSchema(
        "CabinSeatMap",
        description: "Native airplane seat map. Pass the whole get_seat_map Query result as `seatMap`, bind `selected` to a "
            + "$variable holding chosen seat designators (string[], e.g. [\"12A\",\"12B\"]), and set maxSeats to the number of travelers.",
        props: [
            .required("seatMap", .any),
            .binding("selected", .array(.string)),
            .optional("maxSeats", .number),
        ]
    )

    @MainActor static let library: ComponentLibrary = ComponentLibrary.openUIChat.addingContent(
        [
            ComponentDefinition(offerPickerSchema) { context in OfferPickerComponent(context: context) },
            ComponentDefinition(cabinSeatMapSchema) { context in CabinSeatMapComponent(context: context) },
        ],
        group: "Trip booking"
    )
    // Every agent answer is a Card: draw it as the design's borderless light-gray card.
    .replacingRenderer(for: "Card") { context in AnyView(LensCardView(context: context)) }
}

/// Runs every Query()/Mutation() in a generated UI. Most go to the backend (POST /tools/{name});
/// `notify_friends` runs on the phone: it opens Messages with the text filled in.
struct LensToolProvider: OpenUIToolProvider {
    struct ToolFailure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    func callTool(_ name: String, arguments: OpenUIObject) async throws -> OpenUIValue {
        await MainActor.run { NotificationCenter.default.post(name: .lensToolCalled, object: name) }
        if name == "notify_friends" {
            let message = arguments["message"]?.stringValue ?? ""
            let status = await FriendNotifier.present(message: message)
            return .object(OpenUIObject([("status", .string(status)), ("message", .string(message))]))
        }
        var request = URLRequest(url: SharedConfig.backendURL.appendingPathComponent("tools/\(name)"))
        request.httpMethod = "POST"
        // Flight searches wait on airlines; bookings can take up to ~2 minutes on Duffel.
        request.timeoutInterval = ["book_trip", "save_to_notion"].contains(name) ? 150 : 45
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data(OpenUIJSON.stringify(OpenUIValue.object(arguments).plainJSON).utf8)
        let (data, response) = try await URLSession.shared.data(for: request)
        let value = try OpenUIJSON.parse(data)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw ToolFailure(message: value["error"]?.stringValue ?? value["detail"]?.stringValue
                              ?? "Request failed (\(http.statusCode))")
        }
        return value
    }
}

/// Presents the Messages composer (or the share sheet where SMS isn't available, e.g. the Simulator).
@MainActor
enum FriendNotifier {
    private final class Delegate: NSObject, MFMessageComposeViewControllerDelegate {
        var continuation: CheckedContinuation<String, Never>?
        func messageComposeViewController(_ controller: MFMessageComposeViewController,
                                          didFinishWith result: MessageComposeResult) {
            controller.dismiss(animated: true)
            continuation?.resume(returning: result == .sent ? "sent" : result == .cancelled ? "cancelled" : "failed")
            continuation = nil
        }
    }

    private static let delegate = Delegate()

    static func present(message: String) async -> String {
        guard let top = topViewController() else { return "unavailable" }
        if MFMessageComposeViewController.canSendText() {
            return await withCheckedContinuation { continuation in
                delegate.continuation = continuation
                let composer = MFMessageComposeViewController()
                composer.body = message
                composer.messageComposeDelegate = delegate
                top.present(composer, animated: true)
            }
        }
        return await withCheckedContinuation { continuation in
            let sheet = UIActivityViewController(activityItems: [message], applicationActivities: nil)
            sheet.completionWithItemsHandler = { _, completed, _, _ in
                continuation.resume(returning: completed ? "sent" : "cancelled")
            }
            top.present(sheet, animated: true)
        }
    }

    private static func topViewController() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        var top = scene?.windows.first { $0.isKeyWindow }?.rootViewController
        while let presented = top?.presentedViewController { top = presented }
        return top
    }
}
