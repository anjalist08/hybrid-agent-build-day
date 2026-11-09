#if DEBUG
import OpenUI
import SwiftUI

/// Debug-only (`--preview-seatmap`): loads a live seat map for the first seat-map-capable flight on
/// the demo route, to check the cabin layout without tapping through the agent flow.
struct SeatMapPreview: View {
    @State private var map: CabinMap?
    @State private var selected: [String] = []
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading) {
                if let map {
                    CabinSeatMapView(map: map, selected: selected, maxSeats: 3) { selected = $0 }
                } else {
                    ProgressView(error ?? "Loading seat map…")
                }
            }
            .padding()
        }
        .task { await load() }
    }

    private func load() async {
        let tools = LensToolProvider()
        do {
            let flights = try await tools.callTool("search_flights", arguments: OpenUIObject([
                ("origin", "SFO"), ("destination", "RNO"), ("depart_date", "2027-01-15"),
                ("return_date", "2027-01-18"), ("passengers", 3),
            ]))
            let offer = flights["options"]?.arrayValue?.first { $0["title"]?.stringValue?.hasPrefix("Duffel Airways") == true }
                ?? flights["options"]?.arrayValue?.first
            guard let id = offer?["id"]?.stringValue else { error = "No flights"; return }
            let value = try await tools.callTool("get_seat_map", arguments: OpenUIObject([("offer_id", .string(id))]))
            let cabin = CabinMap(value)
            map = cabin
            let cells: [CabinMap.Cell] = cabin.rows.flatMap { row in row.sections.flatMap { $0 } }
            let free: [String] = cells.filter { $0.available }.compactMap { $0.id }
            selected = Array(free.prefix(2))
        } catch {
            self.error = error.localizedDescription
        }
    }
}
#endif
