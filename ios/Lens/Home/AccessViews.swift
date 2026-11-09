import SwiftUI

/// What the on-device AI may use. Everything starts off; stored on the phone only.
enum AccessSettings {
    enum Source: String, CaseIterable, Identifiable {
        case sharedChats, screen, mail, calendar, photos
        var id: String { rawValue }

        var title: String {
            switch self {
            case .sharedChats: return "Shared chats"
            case .screen: return "Screen memory"
            case .mail: return "Mail"
            case .calendar: return "Calendar"
            case .photos: return "Photos"
            }
        }

        var detail: String {
            switch self {
            case .sharedChats: return "Group chats and emails you share with Lens"
            case .screen: return "What you read and watch, read on your Mac"
            case .mail: return "Emails and reservations"
            case .calendar: return "Events and availability"
            case .photos: return "Photos you choose to share"
            }
        }
    }

    static func isOn(_ source: Source) -> Bool {
        SharedConfig.defaults.bool(forKey: "access." + source.rawValue)
    }

    static func set(_ source: Source, _ on: Bool) {
        SharedConfig.defaults.set(on, forKey: "access." + source.rawValue)
    }
}

/// "App access" — choose what the on-device AI can use.
struct AppAccessView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var values: [AccessSettings.Source: Bool] = [:]
    @State private var backendURL = SharedConfig.backendURL.absoluteString
    @State private var showRoutes = false
    @State private var showClassic = false
    @StateObject private var capture = ScreenCaptureController()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Breadcrumb(title: nil) { save(); dismiss() }.padding(.bottom, 24)
                Text("App access").font(.largeTitle.bold()).foregroundStyle(LensDesign.ink)
                Text("Choose what your on-device AI can use.").foregroundStyle(LensDesign.muted).padding(.bottom, 16)

                VStack(spacing: 0) {
                    ForEach(AccessSettings.Source.allCases) { source in
                        if source == .screen {
                            // The real switch: starts/stops the Lens Capture broadcast.
                            ScreenCaptureRow(controller: capture)
                        } else {
                            Toggle(isOn: binding(source)) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(source.title).font(.body).foregroundStyle(LensDesign.ink)
                                    Text(source.detail).font(.footnote).foregroundStyle(LensDesign.muted)
                                }
                            }
                            .tint(LensDesign.blue)
                            .padding(.vertical, 12)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 6)
                .background(LensDesign.surface, in: RoundedRectangle(cornerRadius: LensDesign.bubbleRadius, style: .continuous))

                ScreenSourcesSection().padding(.top, 20)

                Text("All sources start off. Screen memory uses iOS screen broadcast — stop it anytime from the red status pill. Screenshots and chats are read on your devices; only the details a task needs go online.")
                    .font(.footnote).foregroundStyle(LensDesign.muted).padding(.top, 8)

                Button("Turn off all access") {
                    for source in AccessSettings.Source.allCases { values[source] = false }
                }
                .buttonStyle(PillButtonStyle(prominent: false, fullWidth: true))
                .padding(.top, 24)

                advanced.padding(.top, 32)
            }
            .padding(.horizontal, 24)
            .padding(.top, 16)
        }
        .background(Color.white)
        .onAppear {
            for source in AccessSettings.Source.allCases { values[source] = AccessSettings.isOn(source) }
            capture.startPolling()
        }
        .onDisappear {
            save()
            capture.stopPolling()
        }
        .sheet(isPresented: $showRoutes) { RoutingView() }
        .sheet(isPresented: $showClassic) { AssistantChatView() }
    }

    private var advanced: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Developer").font(.headline)
            TextField("Lens server", text: $backendURL)
                .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                .padding(12)
                .background(LensDesign.surface, in: RoundedRectangle(cornerRadius: 12))
            HStack(spacing: 16) {
                Button("Where it ran") { showRoutes = true }
                Button("Memory chat") { showClassic = true }
            }
            .font(.subheadline)
        }
    }

    private func binding(_ source: AccessSettings.Source) -> Binding<Bool> {
        Binding(get: { values[source] ?? false }, set: { values[source] = $0 })
    }

    private func save() {
        for (source, on) in values { AccessSettings.set(source, on) }
        if backendURL != SharedConfig.backendURL.absoluteString { SharedConfig.setBackendURL(backendURL) }
    }
}

/// "Use your shared messages?" — asked only when a task needs it.
struct PermissionView: View {
    let onAllow: () -> Void
    let onContinueWithout: () -> Void
    let onBack: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Breadcrumb(title: nil, onBack: onBack).padding(.bottom, 24)
            Text("Use your shared chat?").font(.largeTitle.bold()).foregroundStyle(LensDesign.ink)
            Text("Read only the plans Alex and Sam shared with you.").foregroundStyle(LensDesign.muted).padding(.bottom, 16)
            VStack(alignment: .leading, spacing: 10) {
                Text("Shared chats access is off").font(.headline)
                Text("Allow your on-device AI to read this group chat. The conversation stays on this device — only trip details go online.")
                Text("You can turn this off in Settings anytime.").font(.footnote).foregroundStyle(LensDesign.muted)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(LensDesign.surface, in: RoundedRectangle(cornerRadius: LensDesign.bubbleRadius, style: .continuous))
            Spacer()
            Button("Allow shared chats", action: onAllow).buttonStyle(PillButtonStyle(fullWidth: true))
            Button("Continue without access", action: onContinueWithout)
                .buttonStyle(PillButtonStyle(prominent: false, fullWidth: true))
        }
        .padding(.horizontal, 24)
        .padding(.top, 16)
        .padding(.bottom, 8)
        .background(Color.white)
    }
}
