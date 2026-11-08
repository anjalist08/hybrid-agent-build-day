import AVFoundation
import Speech

/// Push-to-talk speech recognition and spoken replies, both on-device.
@MainActor
final class VoiceController: NSObject, ObservableObject {
    @Published var transcript = ""
    @Published var isListening = false
    @Published var isSpeaking = false
    @Published var permissionError: String?
    /// True when the recognizer is running without a network round-trip (shown in the routing panel).
    @Published var onDevice = false

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let synthesizer = AVSpeechSynthesizer()

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    func requestPermissions() async {
        let speech = await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { cont.resume(returning: $0) }
        }
        let mic = await AVAudioApplication.requestRecordPermission()
        if speech != .authorized || !mic {
            permissionError = "Enable Microphone and Speech Recognition for Lens in Settings."
        }
    }

    func startListening() {
        guard !isListening, let recognizer, recognizer.isAvailable else { return }
        stopSpeaking()
        transcript = ""
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .duckOthers])
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            onDevice = recognizer.supportsOnDeviceRecognition
            request.requiresOnDeviceRecognition = onDevice
            self.request = request

            let input = audioEngine.inputNode
            input.removeTap(onBus: 0)
            input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) { buffer, _ in
                request.append(buffer)
            }
            audioEngine.prepare()
            try audioEngine.start()
            isListening = true

            task = recognizer.recognitionTask(with: request) { [weak self] result, _ in
                guard let result else { return }
                let text = result.bestTranscription.formattedString
                Task { @MainActor in self?.transcript = text }
            }
        } catch {
            permissionError = "Couldn't start the microphone: \(error.localizedDescription)"
            teardown()
        }
    }

    /// Stops listening and returns the final transcript.
    func stopListening() async -> String {
        guard isListening else { return transcript }
        request?.endAudio()
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        // Give the recognizer a moment to deliver the final words.
        try? await Task.sleep(for: .milliseconds(350))
        teardown()
        return transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func teardown() {
        task?.cancel()
        task = nil
        request = nil
        isListening = false
    }

    func speak(_ text: String) {
        guard !text.isEmpty else { return }
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        try? session.setActive(true)
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = 0.52
        isSpeaking = true
        synthesizer.speak(utterance)
    }

    func stopSpeaking() {
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        isSpeaking = false
    }
}

extension VoiceController: AVSpeechSynthesizerDelegate {
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in self.isSpeaking = false }
    }
}
