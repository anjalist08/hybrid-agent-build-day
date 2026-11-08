import OpenUI
import SwiftUI

/// `SeatMap(seats, $selected, maxSeats)` — renders the get_seats result natively and writes the
/// chosen seat ids into the bound `$selected` variable, which the generated UI reads (selection
/// text, hold_seats Mutation args).
struct SeatMapComponent: View {
    let context: ComponentContext

    var body: some View {
        let props = context.props
        let data = SeatMapData(props["seats"])
        let field = context.runtime.stateField(name: "selected", binding: props["selected"], formName: nil)
        let selected = Set(field.value?.arrayValue?.compactMap(\.stringValue) ?? [])
        let maxSeats = Int(props.number("maxSeats") ?? 8)

        SeatMapView(data: data, selected: selected, maxSeats: maxSeats) { newSelection in
            field.set(.array(newSelection.map { .string($0) }))
        }
    }
}

struct SeatMapData {
    struct Seat: Identifiable {
        let id: String
        let section: String
        let row: String
        let seat: String
        let x: Double
        let y: Double
        let category: String
        let price: Double
        let status: String
    }

    struct Category: Identifiable {
        let id: String
        let label: String
        let color: Color
        let price: Double
    }

    let seats: [Seat]
    let categories: [Category]
    let width: Double
    let height: Double

    init(_ value: OpenUIValue?) {
        let object = value?.objectValue
        width = object?["width"]?.numberValue ?? 0
        height = object?["height"]?.numberValue ?? 0
        categories = (object?["categories"]?.arrayValue ?? []).compactMap { c in
            guard let key = c["key"]?.stringValue else { return nil }
            return Category(id: key, label: c["label"]?.stringValue ?? key,
                            color: Color(hex: c["color"]?.stringValue ?? "") ?? .accentColor,
                            price: c["price"]?.numberValue ?? 0)
        }
        seats = (object?["seats"]?.arrayValue ?? []).compactMap { s in
            guard let id = s["id"]?.stringValue else { return nil }
            return Seat(id: id, section: s["section"]?.stringValue ?? "", row: s["row"]?.stringValue ?? "",
                        seat: s["seat"]?.stringValue ?? "", x: s["x"]?.numberValue ?? 0, y: s["y"]?.numberValue ?? 0,
                        category: s["category"]?.stringValue ?? "", price: s["price"]?.numberValue ?? 0,
                        status: s["status"]?.stringValue ?? "free")
        }
    }

    func color(for category: String) -> Color {
        categories.first { $0.id == category }?.color ?? .accentColor
    }
}

struct SeatMapView: View {
    let data: SeatMapData
    let selected: Set<String>
    let maxSeats: Int
    let onChange: ([String]) -> Void

    @State private var order: [String] = []  // selection order, so the newest replaces the oldest at the cap
    @State private var focused: SeatMapData.Seat?

    private let padding: CGFloat = 14
    private let stageHeight: CGFloat = 26

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if data.seats.isEmpty {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("Loading seats…").font(.subheadline).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 160)
            } else {
                map
                legend
                if let focused {
                    Text("\(focused.section) · Row \(focused.row) · Seat \(focused.seat) — $\(Int(focused.price))")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private var map: some View {
        GeometryReader { geo in
            let scale = (geo.size.width - padding * 2) / max(data.width, 1)
            let radius = max(3, min(7, scale * 5.5))
            Canvas { ctx, size in
                // Stage
                let stage = CGRect(x: size.width * 0.25, y: 0, width: size.width * 0.5, height: stageHeight - 8)
                ctx.fill(Path(roundedRect: stage, cornerRadius: 6), with: .color(.primary.opacity(0.85)))
                ctx.draw(Text("STAGE").font(.caption2.weight(.bold)).foregroundStyle(.white),
                         at: CGPoint(x: stage.midX, y: stage.midY))

                for seat in data.seats {
                    let p = point(seat, scale: scale)
                    let rect = CGRect(x: p.x - radius, y: p.y - radius, width: radius * 2, height: radius * 2)
                    let circle = Path(ellipseIn: rect)
                    if selected.contains(seat.id) {
                        ctx.fill(circle, with: .color(.primary))
                        ctx.stroke(Path(ellipseIn: rect.insetBy(dx: -2, dy: -2)), with: .color(.primary), lineWidth: 1.5)
                    } else if seat.status == "free" {
                        ctx.fill(circle, with: .color(data.color(for: seat.category)))
                    } else {
                        ctx.fill(circle, with: .color(Color(.systemGray4)))
                    }
                }
            }
            .contentShape(Rectangle())
            .gesture(SpatialTapGesture().onEnded { tap in
                handleTap(at: tap.location, scale: scale, radius: radius)
            })
        }
        // Height follows the venue's real proportions at whatever width the card has.
        .aspectRatio(aspectRatio, contentMode: .fit)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Seat map, \(selected.count) selected")
    }

    /// width / height of the drawn map, assuming a ~330pt wide card for the fixed stage and padding.
    private var aspectRatio: CGFloat {
        let drawWidth: CGFloat = 330 - padding * 2
        let drawHeight = drawWidth * CGFloat(data.height / max(data.width, 1))
        return 330 / (stageHeight + padding * 2 + drawHeight)
    }

    private func point(_ seat: SeatMapData.Seat, scale: CGFloat) -> CGPoint {
        CGPoint(x: padding + seat.x * scale, y: stageHeight + padding + seat.y * scale)
    }

    private var legend: some View {
        ViewThatFits(in: .horizontal) {
            legendRow
            VStack(alignment: .leading, spacing: 4) { legendRow }
        }
    }

    private var legendRow: some View {
        HStack(spacing: 10) {
            ForEach(data.categories) { c in
                HStack(spacing: 4) {
                    Circle().fill(c.color).frame(width: 9, height: 9)
                    Text("\(c.label) $\(Int(c.price))").font(.caption2).fixedSize()
                }
            }
            HStack(spacing: 4) {
                Circle().fill(Color(.systemGray4)).frame(width: 9, height: 9)
                Text("Taken").font(.caption2).fixedSize()
            }
        }
        .foregroundStyle(.secondary)
    }

    private func handleTap(at location: CGPoint, scale: CGFloat, radius: CGFloat) {
        let hit = data.seats.min { a, b in
            distance(point(a, scale: scale), location) < distance(point(b, scale: scale), location)
        }
        guard let seat = hit, distance(point(seat, scale: scale), location) <= radius * 2.2 else { return }
        focused = seat
        guard seat.status == "free" else {
            UINotificationFeedbackGenerator().notificationOccurred(.warning)
            return
        }
        var current = order.filter { selected.contains($0) }
        current += selected.filter { !current.contains($0) }.sorted()
        if let index = current.firstIndex(of: seat.id) {
            current.remove(at: index)
        } else {
            current.append(seat.id)
            if current.count > maxSeats { current.removeFirst(current.count - maxSeats) }
        }
        order = current
        UISelectionFeedbackGenerator().selectionChanged()
        onChange(current)
    }

    private func distance(_ a: CGPoint, _ b: CGPoint) -> CGFloat {
        hypot(a.x - b.x, a.y - b.y)
    }
}

extension Color {
    init?(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("#") { s.removeFirst() }
        guard s.count == 6, let v = UInt32(s, radix: 16) else { return nil }
        self.init(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255, blue: Double(v & 0xFF) / 255)
    }
}
