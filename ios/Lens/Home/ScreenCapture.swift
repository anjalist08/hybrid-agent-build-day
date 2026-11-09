import ReplayKit
import SwiftUI

/// Starts/stops the Lens Capture broadcast from our own buttons.
///
/// iOS only lets apps start a screen broadcast through `RPSystemBroadcastPickerView`. We keep
/// one (invisible) picker in the view hierarchy and press its internal button, which opens the
/// system "Screen Broadcast" sheet with Lens Capture preselected.
@MainActor
final class ScreenCaptureController: ObservableObject {
    @Published private(set) var isCapturing = false
    @Published private(set) var framesSent = 0
    @Published private(set) var uploadError: String?

    fileprivate weak var picker: RPSystemBroadcastPickerView?
    private var timer: Timer?

    /// Opens the system sheet (Start Broadcast, or Stop Broadcast when already capturing).
    func toggle() {
        guard let button = picker?.subviews.compactMap({ $0 as? UIButton }).first else { return }
        button.sendActions(for: .touchUpInside)
    }

    func startPolling() {
        refresh()
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.refresh() }
        }
    }

    func stopPolling() {
        timer?.invalidate()
        timer = nil
    }

    private func refresh() {
        let d = SharedConfig.defaults
        // `UIScreen.isCaptured` is true while any recording/broadcast runs; the extension's flag
        // tells us it's ours.
        isCapturing = d.bool(forKey: SharedConfig.Keys.broadcasting) && UIScreen.main.isCaptured
        framesSent = d.integer(forKey: SharedConfig.Keys.framesSent)
        uploadError = d.string(forKey: SharedConfig.Keys.lastUploadError)
    }

    var statusText: String {
        if let uploadError, isCapturing { return "Can't reach the Lens server: \(uploadError)" }
        if isCapturing { return "Capturing · \(framesSent) screen\(framesSent == 1 ? "" : "s") sent to your Mac" }
        return "What you read and watch, read on your Mac"
    }
}

/// The hidden system picker the controller presses. Put it once in each screen that offers capture.
struct ScreenCaptureHost: UIViewRepresentable {
    let controller: ScreenCaptureController

    func makeUIView(context: Context) -> RPSystemBroadcastPickerView {
        let picker = RPSystemBroadcastPickerView(frame: CGRect(x: 0, y: 0, width: 1, height: 1))
        picker.preferredExtension = (Bundle.main.bundleIdentifier ?? "") + ".broadcast"
        picker.showsMicrophoneButton = false
        picker.alpha = 0.011
        controller.picker = picker
        return picker
    }

    func updateUIView(_ uiView: RPSystemBroadcastPickerView, context: Context) {
        controller.picker = uiView
    }
}

/// Settings row: a switch that reflects whether Lens Capture is running and opens the system sheet.
struct ScreenCaptureRow: View {
    @ObservedObject var controller: ScreenCaptureController

    var body: some View {
        Toggle(isOn: Binding(get: { controller.isCapturing }, set: { _ in controller.toggle() })) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text("Screen memory").font(.body).foregroundStyle(LensDesign.ink)
                    if controller.isCapturing {
                        Circle().fill(.red).frame(width: 7, height: 7)
                    }
                }
                Text(controller.statusText)
                    .font(.footnote)
                    .foregroundStyle(controller.uploadError != nil && controller.isCapturing ? .red : LensDesign.muted)
            }
        }
        .tint(LensDesign.blue)
        .padding(.vertical, 12)
        .background(ScreenCaptureHost(controller: controller).frame(width: 1, height: 1), alignment: .topLeading)
    }
}
