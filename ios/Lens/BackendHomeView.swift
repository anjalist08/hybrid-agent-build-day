import SwiftUI

@MainActor
final class BackendHomeModel: ObservableObject {
    @Published private(set) var health: Health?
    @Published private(set) var interests: [MemoryInterest] = []
    @Published private(set) var impressions: [MemoryImpression] = []
    @Published private(set) var isLoading = false
    @Published private(set) var error: String?
    @Published private(set) var updatedAt: Date?
    @Published private(set) var endpoint = ""
    private var generation = 0

    func load() async {
        generation += 1
        let current = generation
        let address = SharedConfig.backendURL.absoluteString
        // Never show the previous server's history under a new server address.
        if endpoint != address {
            health = nil; interests = []; impressions = []; updatedAt = nil
        }
        endpoint = address
        isLoading = true
        error = nil
        defer { if current == generation { isLoading = false } }
        do {
            async let status = LensAPI.health()
            async let topics = LensAPI.interests()
            async let history = LensAPI.impressions()
            let result = try await (status, topics, history)
            guard current == generation, !Task.isCancelled else { return }
            guard result.0.ok else { throw LensAPIError.server(503, "Backend is not ready") }
            health = result.0
            interests = result.1.filter { $0.type == "topic" }
            impressions = result.2
            updatedAt = Date()
        } catch {
            guard current == generation else { return }
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
    }
}

struct BackendHomeView: View {
    let plan: ConcertDemoPlan?
    let refreshID: UUID
    let onAsk: (String) -> Void
    let onOpenDemo: () -> Void
    @StateObject private var model = BackendHomeModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                VStack(alignment: .leading, spacing: 12) {
                    Text("LENS").font(.caption.weight(.bold)).tracking(4).foregroundStyle(.gray)
                    Text("A little more\nof what matters.")
                        .font(.system(size: 36, weight: .medium)).tracking(-1)
                    Text("Your recent context, brought together.")
                        .font(.subheadline).foregroundStyle(.gray)
                }.padding(.top, 24)
                connection
                if let plan {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Your sample Friday plan", systemImage: "calendar")
                            .font(.headline)
                        Text("2 × \(plan.seating) · $\(plan.pricePerTicket * 2) before fees")
                        Text("Demo only · Nothing booked or sent")
                            .font(.caption).foregroundStyle(.gray)
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(white: 0.1), in: RoundedRectangle(cornerRadius: 18))
                }
                if model.health?.fakeMode == true {
                    Label("Demo data · Fictional history · No AI calls", systemImage: "flask")
                        .font(.caption.weight(.medium)).foregroundStyle(.orange)
                }
                if model.updatedAt != nil {
                    topics
                    history
                    Button {
                        onAsk("What have I been reading and watching lately?")
                    } label: {
                        Label("Ask about my activity", systemImage: "waveform")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity).padding(18)
                            .background(.white, in: Capsule()).foregroundStyle(.black)
                    }.buttonStyle(.plain)
                    Text(model.health?.fakeMode == true
                         ? "Questions use the real /query endpoint with fixed demo answers. No AI or external actions."
                         : "Questions use the configured backend's /query endpoint. It may send extracted text to its cloud model.")
                        .font(.caption).foregroundStyle(.gray)
                }
                Divider().overlay(.gray)
                Button(action: onOpenDemo) {
                    HStack {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Concert walkthrough").font(.headline)
                            Text("UI demo · Fictional event and tickets")
                                .font(.caption).foregroundStyle(.gray)
                        }
                        Spacer()
                        Image(systemName: "arrow.up.right")
                    }.padding(.vertical, 8)
                }.buttonStyle(.plain)
                Text("Pull to refresh your backend history. Home reads do not call the cloud model.")
                    .font(.caption2).foregroundStyle(.gray)
            }
            .padding(.horizontal, 26).padding(.bottom, 30)
            .frame(maxWidth: 600).frame(maxWidth: .infinity)
        }
        .foregroundStyle(.white)
        .background(Color.black)
        .toolbarBackground(Color.black, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .task(id: refreshID) { await model.load() }
        .refreshable { await model.load() }
    }

    private var connection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                if model.isLoading { ProgressView().tint(.white) }
                else { Circle().fill(model.error == nil ? Color.green : Color.orange).frame(width: 7, height: 7) }
                Text(model.isLoading ? "Connecting to your backend…" : model.error == nil ? "Backend connected" : "Connection needs attention")
                    .font(.subheadline.weight(.semibold))
            }
            Text(model.endpoint).font(.caption.monospaced()).foregroundStyle(.gray)
                .textSelection(.enabled)
            if let error = model.error {
                Text(error).font(.caption).foregroundStyle(.orange)
                if model.updatedAt != nil {
                    Text("Showing the last successful refresh.").font(.caption).foregroundStyle(.gray)
                }
                Button("Retry connection") { Task { await model.load() } }
                    .font(.subheadline.weight(.semibold)).disabled(model.isLoading)
            } else if let health = model.health {
                Text("\(health.processed) frames read · \(health.queue) queued · \(health.extractor) extractor")
                    .font(.caption).foregroundStyle(.gray)
            }
            if let updatedAt = model.updatedAt {
                Text("Updated \(updatedAt.formatted(date: .omitted, time: .shortened))")
                    .font(.caption2).foregroundStyle(.gray)
            }
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(white: 0.1), in: RoundedRectangle(cornerRadius: 18))
    }

    private var topics: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("On your mind").font(.title2.weight(.medium))
            if model.interests.isEmpty {
                Text("No interests yet. Start screen capture to build your context.")
                    .font(.subheadline).foregroundStyle(.gray)
            } else {
                ForEach(Array(model.interests.prefix(5))) { topic in
                    Button { onAsk("What have I been reading or watching about \(topic.name)?") } label: {
                        HStack {
                            Text(topic.name.capitalized).font(.subheadline.weight(.medium))
                            Spacer()
                            Text("\(topic.impressions) items").font(.caption).foregroundStyle(.gray)
                            Image(systemName: "arrow.up.right").font(.caption)
                        }.padding(.vertical, 12)
                    }.buttonStyle(.plain)
                    Divider().overlay(Color(white: 0.2))
                }
            }
        }
    }

    private var history: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Recently seen").font(.title2.weight(.medium))
            if model.impressions.isEmpty {
                Text("Your backend has no captured activity yet. Use the waveform button to open the assistant and start screen capture.")
                    .font(.subheadline).foregroundStyle(.gray)
            } else {
                ForEach(Array(model.impressions.prefix(5))) { item in
                    Button { onAsk("Tell me about this item from my history: \(item.title)") } label: {
                        VStack(alignment: .leading, spacing: 9) {
                            HStack {
                                Text(item.app.uppercased()).tracking(1)
                                Spacer()
                                Text(Date(timeIntervalSince1970: item.tsEnd), style: .relative)
                            }.font(.caption2).foregroundStyle(.gray)
                            Text(item.title).font(.subheadline.weight(.medium)).multilineTextAlignment(.leading)
                            if let author = item.author { Text(author).font(.caption).foregroundStyle(.gray) }
                            Label("Ask Lens about this", systemImage: "arrow.up.right")
                                .font(.caption).foregroundStyle(Color(white: 0.75))
                        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color(white: 0.08), in: RoundedRectangle(cornerRadius: 18))
                    }.buttonStyle(.plain)
                }
            }
        }
    }
}
