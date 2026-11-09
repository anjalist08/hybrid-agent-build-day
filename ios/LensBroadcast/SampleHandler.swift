import CoreImage
import ReplayKit
import os

/// Broadcast Upload Extension: receives every screen frame while the user is in any app,
/// keeps one every `SharedConfig.captureInterval` seconds, downsizes it to a JPEG and
/// posts it to the backend. The extension has a ~50MB memory cap, so it does nothing heavier.
final class SampleHandler: RPBroadcastSampleHandler {
    private let ciContext = CIContext(options: [.cacheIntermediates: false])
    private let colorSpace = CGColorSpaceCreateDeviceRGB()
    private let state = OSAllocatedUnfairLock(initialState: (lastSent: 0.0, inFlight: 0))
    private let deviceID = "iphone"
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.httpMaximumConnectionsPerHost = 2
        return URLSession(configuration: config)
    }()

    override func broadcastStarted(withSetupInfo setupInfo: [String: NSObject]?) {
        SharedConfig.defaults.set(true, forKey: SharedConfig.Keys.broadcasting)
        SharedConfig.defaults.set(0, forKey: SharedConfig.Keys.framesSent)
        SharedConfig.defaults.removeObject(forKey: SharedConfig.Keys.lastUploadError)
    }

    override func broadcastFinished() {
        SharedConfig.defaults.set(false, forKey: SharedConfig.Keys.broadcasting)
    }

    override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, with sampleBufferType: RPSampleBufferType) {
        guard sampleBufferType == .video else { return }
        // Don't record Lens's own screens (the app refreshes this heartbeat while it's in front).
        let lensUntil = SharedConfig.defaults.double(forKey: SharedConfig.Keys.lensForegroundUntil)
        guard Date().timeIntervalSince1970 > lensUntil else { return }

        let now = CFAbsoluteTimeGetCurrent()
        let interval = SharedConfig.captureInterval
        let shouldSend = state.withLock { s -> Bool in
            guard now - s.lastSent >= interval, s.inFlight < 2 else { return false }
            s.lastSent = now
            s.inFlight += 1
            return true
        }
        guard shouldSend else { return }

        let jpeg: Data? = autoreleasepool { encode(sampleBuffer) }
        guard let jpeg else {
            state.withLock { $0.inFlight -= 1 }
            return
        }
        upload(jpeg, ts: Date().timeIntervalSince1970)
    }

    private func encode(_ sampleBuffer: CMSampleBuffer) -> Data? {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return nil }
        var image = CIImage(cvPixelBuffer: pixelBuffer)
        if let raw = CMGetAttachment(sampleBuffer, key: RPVideoSampleOrientationKey as CFString, attachmentModeOut: nil) as? NSNumber,
           let orientation = CGImagePropertyOrientation(rawValue: raw.uint32Value) {
            image = image.oriented(orientation)
        }
        // ~1280px on the long side is plenty for reading titles and handles.
        let scale = 1280 / max(image.extent.width, image.extent.height)
        if scale < 1 {
            image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        }
        let quality = kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption
        return ciContext.jpegRepresentation(of: image, colorSpace: colorSpace, options: [quality: 0.6])
    }

    private func upload(_ jpeg: Data, ts: TimeInterval) {
        let boundary = "lens-\(UUID().uuidString)"
        var request = URLRequest(url: SharedConfig.backendURL.appendingPathComponent("ingest/frame"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        func append(_ s: String) { body.append(Data(s.utf8)) }
        for (name, value) in [("ts", String(ts)), ("device", deviceID)] {
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n")
        }
        append("--\(boundary)\r\nContent-Disposition: form-data; name=\"frame\"; filename=\"frame.jpg\"\r\n")
        append("Content-Type: image/jpeg\r\n\r\n")
        body.append(jpeg)
        append("\r\n--\(boundary)--\r\n")

        session.uploadTask(with: request, from: body) { [state] _, response, error in
            state.withLock { $0.inFlight -= 1 }
            let defaults = SharedConfig.defaults
            if let error {
                defaults.set(error.localizedDescription, forKey: SharedConfig.Keys.lastUploadError)
            } else if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                defaults.set("HTTP \(http.statusCode)", forKey: SharedConfig.Keys.lastUploadError)
            } else {
                defaults.set(defaults.integer(forKey: SharedConfig.Keys.framesSent) + 1, forKey: SharedConfig.Keys.framesSent)
                defaults.removeObject(forKey: SharedConfig.Keys.lastUploadError)
            }
        }.resume()
    }
}
