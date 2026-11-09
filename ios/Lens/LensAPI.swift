import Foundation

// Mirrors backend/app/schemas.py. Keep in sync.

struct QueryResponse: Decodable {
    let answer: LensAnswer
    let route: RouteInfo
}

struct RouteInfo: Decodable {
    let location: String
    let model: String
    let ms: Int
    let impressionsSent: Int?
    let imagesSent: Int?
    let transcriptSource: String?
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
}
