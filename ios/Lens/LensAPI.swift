import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

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
    let fakeMode: Bool?
    let extractor: String
    let queue: Int
    let received: Int
    let deduped: Int
    let processed: Int
    let failed: Int
}

struct MemoryInterest: Decodable, Identifiable {
    let type: String
    let name: String
    let score: Double
    let impressions: Int
    let dwellS: Double
    var id: String { type + ":" + name }
}

struct MemoryImpression: Decodable, Identifiable {
    let id: Int
    let app: String
    let kind: String
    let title: String
    let author: String?
    let summary: String?
    let tsEnd: Double
    let dwellS: Double
}

enum LensAPIError: LocalizedError {
    case server(Int, String)
    case invalidURL
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Enter a valid http:// or https:// backend address."
        case .invalidResponse: return "The backend returned an invalid response."
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
                                           timeout: TimeInterval = 60, baseURL: URL = SharedConfig.backendURL,
                                           query: [URLQueryItem] = []) async throws -> T {
        guard ["http", "https"].contains(baseURL.scheme?.lowercased() ?? ""), baseURL.host != nil,
              var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else {
            throw LensAPIError.invalidURL
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw LensAPIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw LensAPIError.invalidResponse }
        if !(200..<300).contains(http.statusCode) {
            throw LensAPIError.server(http.statusCode, String(decoding: data, as: UTF8.self))
        }
        return try decoder.decode(T.self, from: data)
    }

    static func query(_ text: String, source: String) async throws -> QueryResponse {
        let body = try JSONSerialization.data(withJSONObject: ["text": text, "source": source])
        return try await send("query", method: "POST", body: body)
    }

    static func interests() async throws -> [MemoryInterest] {
        try await send("interests", query: [URLQueryItem(name: "type", value: "topic"), URLQueryItem(name: "limit", value: "5")])
    }

    static func impressions() async throws -> [MemoryImpression] {
        try await send("impressions", query: [URLQueryItem(name: "limit", value: "5")])
    }

    static func routes() async throws -> [RouteLogEntry] {
        try await send("routes")
    }

    static func health(baseURL: URL = SharedConfig.backendURL) async throws -> Health {
        try await send("health", timeout: 5, baseURL: baseURL)
    }
}
