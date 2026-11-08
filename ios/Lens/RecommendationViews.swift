import SwiftUI

private enum RecommendationStyle {
    static let background = Color.white
    static let accent = Color(red: 0.50, green: 0.36, blue: 0.85)
    static let ink = Color(red: 0.12, green: 0.12, blue: 0.11)
}

/// Personal suggestions are sample content until live recommendation APIs are connected.
struct RecommendationHomeView: View {
    let onOpenConcert: () -> Void

    @State private var dismissedConcert = false
    @State private var previewMessage: String?

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                VStack(spacing: 7) {
                    Image(systemName: "lock.fill").font(.system(size: 15)).padding(.bottom, 8)
                    Text("9:41").font(.system(size: 78, weight: .light)).tracking(-3)
                    Text("Thursday, November 12").font(.system(size: 17, weight: .medium))
                }
                .frame(maxWidth: .infinity).padding(.top, 32).padding(.bottom, 52)

                if !dismissedConcert {
                    suggestion(title: "Friday night", time: "now", text: "Your favorite artist is playing Friday, and your calendar is clear. Interested?") {
                        HStack(spacing: 24) {
                            Button("Take a look", action: onOpenConcert)
                                .foregroundStyle(.white).fontWeight(.semibold)
                            Button("Not now") { withAnimation { dismissedConcert = true } }
                                .foregroundStyle(.gray)
                        }
                    }
                }
                suggestion(title: "Commute", time: "8 min ago", text: "Rain expected at 10 am. Your usual route adds 12 min — leave by 9:50?") {
                    Button("See route") { previewMessage = "Route preview is not connected in this demo." }
                        .foregroundStyle(.white).fontWeight(.semibold)
                }
                suggestion(title: "Reading", time: "saved Tuesday", text: "You saved an article on flow states. 6 min read — quiet morning to catch up.") {
                    Button("Open article") { previewMessage = "Saved article preview is not connected in this demo." }
                        .foregroundStyle(.white).fontWeight(.semibold)
                }
                Spacer(minLength: 38)
                HStack(spacing: 7) {
                    Image(systemName: "lock.shield").font(.system(size: 11))
                    Text("Only for you. On your device.").font(.system(size: 11))
                    Spacer()
                    Text("DEMO").font(.system(size: 9, weight: .medium)).tracking(1)
                }.foregroundStyle(.gray).padding(.top, 28)
            }
            .padding(.horizontal, 30).padding(.bottom, 28)
            .frame(maxWidth: 560).frame(maxWidth: .infinity)
        }
        .foregroundStyle(.white)
        .background(Color.black)
        .toolbarBackground(Color.black, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .alert("Demo preview", isPresented: Binding(get: { previewMessage != nil }, set: { if !$0 { previewMessage = nil } })) {
            Button("OK", role: .cancel) { previewMessage = nil }
        } message: {
            Text(previewMessage ?? "")
        }
    }

    private func suggestion<Action: View>(title: String, time: String, text: String, @ViewBuilder action: () -> Action) -> some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack {
                Text(title).font(.system(size: 14, weight: .semibold))
                Spacer()
                Text(time).font(.system(size: 11)).foregroundStyle(.gray)
            }
            Text(text).font(.system(size: 17)).foregroundStyle(Color(white: 0.75)).lineSpacing(6)
                .fixedSize(horizontal: false, vertical: true)
            action().font(.system(size: 13)).padding(.top, 3)
        }
        .padding(.vertical, 25)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .top) { Rectangle().fill(Color(white: 0.23)).frame(height: 0.5) }
    }
}

struct ConcertDetailView: View {
    let onFindTickets: () -> Void

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 24) {
                ConcertArtwork().frame(height: 270)
                    .clipShape(RoundedRectangle(cornerRadius: 26))
                VStack(alignment: .leading, spacing: 12) {
                    Text("A LITTLE SERENDIPITY").font(.system(size: 10, weight: .bold)).tracking(2)
                        .foregroundStyle(RecommendationStyle.accent)
                    Text("This Friday has\nyour name on it.")
                        .font(.system(size: 39, weight: .medium, design: .serif)).tracking(-1.3)
                    Text("You've been making room for more live music. Here's a night that could be just right.")
                        .font(.subheadline).foregroundStyle(.secondary).lineSpacing(5)
                }

                VStack(spacing: 17) {
                    detailRow("calendar", title: "Friday evening", subtitle: "Doors at 6:30 PM · Show at 7:30 PM")
                    Divider()
                    detailRow("music.note.house", title: "A live concert near you", subtitle: "Sample event · Live availability is not connected")
                    Divider()
                    detailRow("person.2", title: "Better with good company", subtitle: "Find a pair of seats, then draft an invite")
                }.padding(20).background(.white, in: RoundedRectangle(cornerRadius: 22))

                VStack(alignment: .leading, spacing: 10) {
                    Label("Why this is here", systemImage: "sparkles").font(.subheadline.weight(.semibold))
                    Text("This demo combines a music interest with an open Friday evening to show how a personal suggestion becomes a plan.")
                        .font(.caption).foregroundStyle(.secondary).lineSpacing(4)
                }.padding(.horizontal, 4)

                Button(action: onFindTickets) {
                    HStack {
                        Text("Find tickets").font(.subheadline.weight(.semibold))
                        Spacer()
                        Image(systemName: "arrow.right")
                    }.foregroundStyle(.white).padding(20)
                        .background(RecommendationStyle.ink, in: Capsule())
                }.buttonStyle(.plain)

                Label("Preview the search disclosure next. Demo stays offline.", systemImage: "lock.shield")
                    .font(.caption2).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
            }
            .padding(24).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }
        .background(RecommendationStyle.background)
        .foregroundStyle(RecommendationStyle.ink)
        .navigationTitle("Made for you")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(Color.white, for: .navigationBar)
        .toolbarColorScheme(.light, for: .navigationBar)
    }

    private func detailRow(_ symbol: String, title: String, subtitle: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: symbol).font(.system(size: 18)).foregroundStyle(RecommendationStyle.accent)
                .frame(width: 24).padding(.top, 2)
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(subtitle).font(.caption).foregroundStyle(.secondary).lineSpacing(3)
            }
            Spacer(minLength: 0)
        }
    }
}

/// A bundled, scalable illustration keeps the demo usable without image downloads.
private struct ConcertArtwork: View {
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                LinearGradient(colors: [Color(red: 0.23, green: 0.10, blue: 0.26), Color(red: 0.65, green: 0.22, blue: 0.22), Color(red: 0.98, green: 0.57, blue: 0.23)], startPoint: .topLeading, endPoint: .bottomTrailing)
                Circle().fill(Color.orange.opacity(0.4)).frame(width: 200, height: 200)
                    .blur(radius: 22).offset(x: 100, y: -50)
                ForEach(0..<7) { index in
                    Rectangle().fill(Color.white.opacity(index.isMultiple(of: 2) ? 0.12 : 0.06))
                        .frame(width: 30, height: geometry.size.height * 1.8)
                        .rotationEffect(.degrees(Double(index * 11 - 35)))
                        .offset(x: CGFloat(index * 43 - 125), y: -60)
                }
                VStack(spacing: 12) {
                    Spacer()
                    Image(systemName: "waveform").font(.system(size: 60, weight: .ultraLight))
                    Text("THE NIGHT IS YOURS").font(.system(size: 11, weight: .semibold)).tracking(4)
                    Spacer().frame(height: 35)
                }.foregroundStyle(Color.white.opacity(0.95))
                HStack(alignment: .bottom, spacing: 9) {
                    ForEach(0..<19) { index in
                        Capsule().fill(Color.black.opacity(0.65))
                            .frame(width: geometry.size.width / 16, height: CGFloat(22 + (index * 13) % 33))
                    }
                }.frame(maxHeight: .infinity, alignment: .bottom).offset(y: 11)
            }.clipped()
        }
        .accessibilityLabel("Warm stage lights over a concert crowd")
    }
}
