import Foundation

/// Settings shared between the app and the broadcast extension through the App Group.
enum SharedConfig {
    static var appGroup: String {
        Bundle.main.object(forInfoDictionaryKey: "LensAppGroup") as? String ?? ""
    }

    static var defaults: UserDefaults {
        UserDefaults(suiteName: appGroup) ?? .standard
    }

    static var backendURL: URL {
        if let s = defaults.string(forKey: Keys.backendURL), let url = URL(string: s), url.scheme != nil {
            return url
        }
        #if targetEnvironment(simulator)
        // The Simulator shares the Mac's network, so the backend is just localhost.
        return URL(string: "http://localhost:8000")!
        #else
        let fallback = Bundle.main.object(forInfoDictionaryKey: "LensBackendURL") as? String ?? "http://localhost:8000"
        return URL(string: fallback) ?? URL(string: "http://localhost:8000")!
        #endif
    }

    static func setBackendURL(_ value: String) {
        defaults.set(value.trimmingCharacters(in: .whitespaces), forKey: Keys.backendURL)
    }

    /// Seconds between screenshots. The local vision model takes ~10-15s per new screen,
    /// and the backend skips duplicate screens, so 5s is a good default.
    static var captureInterval: TimeInterval {
        get { let v = defaults.double(forKey: Keys.captureInterval); return v > 0 ? v : 5 }
        set { defaults.set(newValue, forKey: Keys.captureInterval) }
    }

    enum Keys {
        static let backendURL = "backendURL"
        static let captureInterval = "captureInterval"
        static let broadcasting = "broadcasting"
        static let framesSent = "framesSent"
        static let lastUploadError = "lastUploadError"
        /// Set by the app while it is on screen, so the broadcast doesn't record Lens itself.
        static let lensForegroundUntil = "lensForegroundUntil"
    }
}
