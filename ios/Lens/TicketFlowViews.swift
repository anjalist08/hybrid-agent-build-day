import SwiftUI

/// A self-contained, local demo. No ticket, messaging, or calendar services are called.
struct TicketFlowView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var step: Step = .request
    @State private var query = "Find two tickets for Friday night, under $150 each."
    @State private var seatedOnly = false
    @State private var selectedTicket = 0
    @State private var includeInvite = true
    @State private var includeCalendar = true
    @State private var rememberSeating = false
    @State private var rememberBudget = false
    private let background = Color.white
    private let accent = Color(red: 0.43, green: 0.30, blue: 0.83)

    private enum Step: Int, CaseIterable {
        case request, permission, searching, tickets, drafts, complete
    }

    private struct Ticket {
        let title: String
        let detail: String
        let price: Int
        let seated: Bool
    }

    private let tickets = [
        Ticket(title: "Lower bowl", detail: "Section 112 · Row 8 · Together", price: 125, seated: true),
        Ticket(title: "Floor admission", detail: "Standing · General admission", price: 95, seated: false),
        Ticket(title: "Upper level", detail: "Section 204 · Row 3 · Together", price: 78, seated: true)
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    HStack(spacing: 6) {
                        ForEach(0..<5) { index in
                            Capsule().fill(index <= progressIndex ? accent : Color.black.opacity(0.09)).frame(height: 3)
                        }
                    }
                    .padding(.top, 12)
                    Label("FRIDAY, MADE EASY", systemImage: "sparkles")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .tracking(1.5)
                        .foregroundStyle(accent)
                    content
                    Text("LOCAL DEMO · No purchases or external actions")
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .padding(.top, 8)
                }
                .padding(24)
                .frame(maxWidth: 600, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .background(background.ignoresSafeArea())
            .foregroundStyle(Color.black)
            .navigationTitle("Lens")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if step != .request && step != .searching && step != .complete {
                        Button { step = step == .tickets ? .permission : Step(rawValue: step.rawValue - 1) ?? .request } label: {
                            Image(systemName: "arrow.left").foregroundStyle(.black)
                        }
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: { Image(systemName: "xmark").foregroundStyle(.black) }
                        .accessibilityLabel("Close ticket demo")
                }
            }
        }
        .tint(accent)
    }

    private var progressIndex: Int { step == .searching ? 1 : max(0, step.rawValue - (step.rawValue > 2 ? 1 : 0)) }

    @ViewBuilder private var content: some View {
        switch step {
        case .request:
            heading("A night out,\nwithout the tabs.", subtitle: "Let's turn that concert idea into a Friday plan.")
            card {
                Label("YOUR REQUEST", systemImage: "waveform").font(.caption.weight(.bold)).foregroundStyle(accent)
                TextField("What would you like to find?", text: $query, axis: .vertical)
                    .font(.title3.weight(.medium)).lineLimit(3...5)
                Text("Type a request to try the demo. Voice recording is not active here.").font(.caption).foregroundStyle(.secondary)
            }
            Label("2 people  ·  Friday evening", systemImage: "person.2").font(.subheadline)
            action("Find a good night out", icon: "arrow.right") { step = .permission }
                .disabled(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        case .permission:
            heading("You're in control.", subtitle: "A real ticket search would need permission to go online.")
            card {
                Label("WHAT WOULD BE SHARED", systemImage: "network").font(.caption.weight(.bold)).foregroundStyle(accent)
                Text("Your search request").font(.headline)
                Text(query).font(.body)
                Divider()
                Text("An online ticket provider would receive the request above, including any artist, date, ticket count, budget, or location you enter. No screen history, contacts, calendar, or saved memories are included.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            Text("This demo stays on your device. Both choices use the same fictional ticket data; no request is sent online.").font(.footnote).foregroundStyle(.secondary)
            action("Allow online search · simulate", icon: "arrow.up.right") { step = .searching }
            Button("Stay offline · view sample tickets") { step = .tickets }
                .font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity)
        case .searching:
            heading("Finding your\nFriday feeling.", subtitle: "Simulating a search for two tickets within your budget.")
            card {
                HStack(spacing: 18) {
                    ProgressView().tint(accent)
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Comparing sample options").font(.headline)
                        Text("Fictional availability · No network request").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            action("Show sample results", icon: "arrow.right") { step = .tickets }
            .task {
                try? await Task.sleep(nanoseconds: 1_200_000_000)
                guard !Task.isCancelled, step == .searching else { return }
                step = .tickets
            }
        case .tickets:
            heading("Your kind\nof seats.", subtitle: "Friday night · 2 tickets · Fictional concert")
            HStack {
                Text("SAMPLE TICKETS").font(.caption.weight(.bold)).foregroundStyle(accent)
                Spacer()
                Toggle("Seated only", isOn: $seatedOnly).font(.caption).fixedSize()
                    .onChange(of: seatedOnly) { _, seated in
                        if seated && !tickets[selectedTicket].seated { selectedTicket = 0 }
                    }
            }
            ForEach(tickets.indices, id: \.self) { index in
                if !seatedOnly || tickets[index].seated {
                    Button { selectedTicket = index } label: {
                        HStack(alignment: .top, spacing: 14) {
                            Image(systemName: selectedTicket == index ? "largecircle.fill.circle" : "circle")
                                .foregroundStyle(selectedTicket == index ? accent : .gray)
                            VStack(alignment: .leading, spacing: 6) {
                                Text(tickets[index].title).font(.headline)
                                Text(tickets[index].detail).font(.caption).foregroundStyle(.secondary)
                                if index == 0 { Text("A little closer to the music").font(.caption).foregroundStyle(accent) }
                            }
                            Spacer(minLength: 0)
                            VStack(alignment: .trailing) {
                                Text("$\(tickets[index].price)").font(.title3.weight(.bold))
                                Text("per ticket").font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        .padding(18).background(.white, in: RoundedRectangle(cornerRadius: 20))
                        .overlay(RoundedRectangle(cornerRadius: 20).stroke(selectedTicket == index ? accent : .clear, lineWidth: 1.5))
                    }.buttonStyle(.plain)
                }
            }
            Text("Demo prices only. Availability, fees, and event details are fictional. No tickets are reserved or purchased.").font(.caption).foregroundStyle(.secondary)
            action("Use this option", icon: "arrow.right") { step = .drafts }
        case .drafts:
            heading("Make it\na plan.", subtitle: "Review a couple of drafts before you wrap up.")
            card {
                Toggle("Invitation draft", isOn: $includeInvite).font(.headline)
                Text("Want to catch a concert Friday? I found two \(tickets[selectedTicket].title.lowercased()) tickets at $\(tickets[selectedTicket].price) each. Shall we go?")
                    .font(.subheadline).foregroundStyle(.secondary)
                Label("No recipient selected · No message will be sent", systemImage: "paperplane").font(.caption).foregroundStyle(accent)
            }
            card {
                Toggle("Calendar draft", isOn: $includeCalendar).font(.headline)
                Text("Friday concert night").font(.subheadline.weight(.semibold))
                Text("Friday · 7:00–10:00 PM\nVenue and event date to be confirmed")
                    .font(.subheadline).foregroundStyle(.secondary)
                Label("Preview only · No calendar access", systemImage: "calendar").font(.caption).foregroundStyle(accent)
            }
            action("Finish demo plan", icon: "checkmark") { step = .complete }
        case .complete:
            Image(systemName: "checkmark.circle.fill").font(.system(size: 48)).foregroundStyle(accent)
            heading("Friday looks\ngood on you.", subtitle: "Your sample plan is ready to review.")
            card {
                Text("CONCERT NIGHT").font(.caption.weight(.bold)).foregroundStyle(accent)
                Text("Friday · 7 PM").font(.title2.weight(.semibold))
                Text("2 × \(tickets[selectedTicket].title) · $\(tickets[selectedTicket].price * 2) sample total, before fees").font(.subheadline)
                Divider()
                Label(includeInvite ? "Invitation draft included" : "Invitation draft skipped", systemImage: "envelope")
                Label(includeCalendar ? "Calendar draft included" : "Calendar draft skipped", systemImage: "calendar")
                Text("Nothing was booked, sent, or added to your calendar.").font(.caption).foregroundStyle(.secondary)
            }
            card {
                Text("Keep this in mind?").font(.headline)
                Text("Optional preferences for this demo session only.").font(.caption).foregroundStyle(.secondary)
                Toggle("I prefer seated tickets", isOn: $rememberSeating)
                Toggle("Keep my budget under $150", isOn: $rememberBudget)
            }
            action("Done", icon: "checkmark") { dismiss() }
        }
    }

    private func heading(_ title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title).font(.system(size: 40, weight: .semibold, design: .rounded)).tracking(-1.6)
                .fixedSize(horizontal: false, vertical: true)
            Text(subtitle).font(.body).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func card<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 16, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(20).background(Color(white: 0.96), in: RoundedRectangle(cornerRadius: 24))
    }

    private func action(_ title: String, icon: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            HStack {
                Text(title).font(.subheadline.weight(.semibold))
                Spacer()
                Image(systemName: icon)
            }
            .foregroundStyle(.white).padding(20)
            .background(Color.black, in: RoundedRectangle(cornerRadius: 20))
        }
        .buttonStyle(.plain)
    }
}
