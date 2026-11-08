import Foundation

// Mirrors backend/app/schemas.py. Keep in sync.

struct QueryResponse: Decodable {
    let answer: LensAnswer
    let route: RouteInfo
}

struct RouteInfo: Decodable {
    let location: String          // "local" or "cloud"
    let model: String
    let ms: Int
    let impressionsSent: Int?
    let imagesSent: Int?
    let transcriptSource: String?
    // Hybrid routing (backend/app/router.py)
    let engine: String?           // "rules" (knowledge base), "ollama" (local model) or "claude"
    let reason: String?           // why it ran where it did
    let offline: Bool?
    let fallbackFrom: String?     // "cloud" when the cloud failed and Lens answered locally
    let charsSent: Int?

    var isLocal: Bool { location != "cloud" }
}

struct ModeInfo: Codable {
    var router: String
    var offline: Bool
}

struct LensAnswer: Decodable {
    let speech: String
    let ui: GenScreen
    let action: LensAction
}

struct LensAction: Decodable {
    let kind: String
    let url: String?
}

struct GenScreen: Decodable {
    let title: String
    let components: [GenComponent]
}

struct GenComponent: Decodable, Identifiable {
    let id = UUID()
    let type: String
    let title: String?
    let subtitle: String?
    let body: String?
    let url: String?
    let items: [GenItem]?
    let bars: [GenBar]?

    private enum CodingKeys: String, CodingKey {
        case type, title, subtitle, body, url, items, bars
    }
}

struct GenItem: Decodable, Hashable {
    let title: String
    let subtitle: String?
    let meta: String?
    let url: String?
}

struct GenBar: Decodable, Hashable {
    let label: String
    let value: Double
}

struct RouteLogEntry: Decodable, Identifiable {
    let id: Int
    let ts: Double
    let op: String
    let location: String
    let model: String?
    let ms: Int?
    let ok: Int
    let detail: String?
}

struct Health: Decodable {
    let ok: Bool
    let extractor: String
    let router: String?
    let offline: Bool?
    let queue: Int
    let received: Int
    let deduped: Int
    let processed: Int
    let failed: Int
}

enum LensAPIError: LocalizedError {
    case server(Int, String)

    var errorDescription: String? {
        switch self {
        case let .server(code, body): return "Backend error \(code): \(body.prefix(200))"
        }
    }
}

enum LensAPI {
    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private static func send<T: Decodable>(_ path: String, method: String = "GET", body: Data? = nil,
                                           timeout: TimeInterval = 60) async throws -> T {
        var request = URLRequest(url: SharedConfig.backendURL.appendingPathComponent(path))
        request.httpMethod = method
        request.timeoutInterval = timeout
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw LensAPIError.server(http.statusCode, String(decoding: data, as: UTF8.self))
        }
        return try decoder.decode(T.self, from: data)
    }

    static func query(_ text: String, source: String) async throws -> QueryResponse {
        let body = try JSONSerialization.data(withJSONObject: ["text": text, "source": source])
        return try await send("query", method: "POST", body: body)
    }

    static func routes() async throws -> [RouteLogEntry] {
        try await send("routes")
    }

    static func health() async throws -> Health {
        try await send("health", timeout: 5)
    }

    static func mode() async throws -> ModeInfo {
        try await send("mode", timeout: 5)
    }

    /// Turn offline mode on or off on the backend (simulates unplugging the network for the demo).
    static func setOffline(_ offline: Bool) async throws -> ModeInfo {
        let body = try JSONSerialization.data(withJSONObject: ["offline": offline])
        return try await send("mode", method: "POST", body: body, timeout: 5)
    }
}
