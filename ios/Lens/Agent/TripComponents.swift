import OpenUI
import SwiftUI

// MARK: - OfferPicker

/// `OfferPicker(options, $selected)` — flights, stays or cars from a search Query, one tappable
/// card each. Writes the chosen option id into the bound $variable (which re-runs dependent
/// Queries such as the seat map and the live total).
struct OfferPickerComponent: View {
    let context: ComponentContext

    var body: some View {
        let props = context.props
        let result = props["options"]
        let options = (result?["options"]?.arrayValue ?? []).compactMap(TripOption.init)
        let kind = result?["kind"]?.stringValue ?? ""
        let source = result?["source"]?.stringValue ?? ""
        let field = context.runtime.stateField(name: "selected", binding: props["selected"], formName: nil)
        let selected = field.value?.stringValue ?? ""

        VStack(alignment: .leading, spacing: 8) {
            if options.isEmpty {
                HStack(spacing: 8) {
                    ProgressView()
                    Text(loadingText(kind)).font(.subheadline).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading)
                .padding(.horizontal, 12)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))
            } else {
                ForEach(options) { option in
                    OfferRow(option: option, isSelected: option.id == selected) {
                        UISelectionFeedbackGenerator().selectionChanged()
                        field.set(.string(option.id))
                    }
                }
                if source == "duffel" {
                    Label("Live from Duffel (test mode)", systemImage: "bolt.horizontal.circle")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
    }

    private func loadingText(_ kind: String) -> String {
        switch kind {
        case "flight": return "Searching airlines…"
        case "stay": return "Finding places to stay…"
        case "car": return "Checking rental cars…"
        default: return "Loading options…"
        }
    }
}

struct TripOption: Identifiable {
    let id: String
    let kind: String
    let title: String
    let subtitle: String
    let detail: String
    let price: Double
    let currency: String
    let badge: String
    let image: String

    init?(_ v: OpenUIValue) {
        guard let id = v["id"]?.stringValue else { return nil }
        self.id = id
        kind = v["kind"]?.stringValue ?? ""
        title = v["title"]?.stringValue ?? ""
        subtitle = v["subtitle"]?.stringValue ?? ""
        detail = v["detail"]?.stringValue ?? ""
        price = v["price"]?.numberValue ?? 0
        currency = v["currency"]?.stringValue ?? "USD"
        badge = v["badge"]?.stringValue ?? ""
        image = v["image"]?.stringValue ?? ""
    }

    var symbol: String {
        switch kind {
        case "flight": return "airplane"
        case "stay": return "bed.double.fill"
        case "car": return "car.fill"
        default: return "circle"
        }
    }

    var priceText: String {
        price.formatted(.currency(code: currency).precision(.fractionLength(0)))
    }
}

private struct OfferRow: View {
    let option: TripOption
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 12) {
                thumbnail
                VStack(alignment: .leading, spacing: 3) {
                    Text(option.title).font(.subheadline.weight(.semibold)).lineLimit(2)
                    Text(option.subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    HStack(spacing: 6) {
                        Text(option.detail).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                        if !option.badge.isEmpty {
                            Text(option.badge)
                                .font(.caption2.weight(.semibold))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(Color.accentColor.opacity(0.12), in: Capsule())
                        }
                    }
                }
                Spacer(minLength: 4)
                VStack(alignment: .trailing, spacing: 6) {
                    Text(option.priceText).font(.headline)
                    Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                        .font(.title3)
                        .foregroundStyle(isSelected ? Color.accentColor : Color(.tertiaryLabel))
                }
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(isSelected ? Color.accentColor.opacity(0.08) : Color(.secondarySystemBackground))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(isSelected ? Color.accentColor : .clear, lineWidth: 1.5)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }

    @ViewBuilder private var thumbnail: some View {
        let placeholder = Image(systemName: option.symbol)
            .font(.title3)
            .foregroundStyle(Color.accentColor)
            .frame(width: 44, height: 44)
            .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
        if let url = URL(string: option.image), !option.image.isEmpty {
            AsyncImage(url: url) { image in
                image.resizable().scaledToFit().padding(option.kind == "flight" ? 6 : 0)
                    .frame(width: 44, height: 44)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 10))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            } placeholder: {
                placeholder
            }
        } else {
            placeholder
        }
    }
}

// MARK: - CabinSeatMap

/// `CabinSeatMap(seatMap, $selected, maxSeats)` — the cabin of the chosen flight from Duffel's
/// seat map: rows of seats split by aisles, paid seats marked with their price.
struct CabinSeatMapComponent: View {
    let context: ComponentContext

    var body: some View {
        let props = context.props
        let map = props["seatMap"]
        let field = context.runtime.stateField(name: "selected", binding: props["selected"], formName: nil)
        let selected = field.value?.arrayValue?.compactMap(\.stringValue) ?? []
        let maxSeats = max(1, Int(props.number("maxSeats") ?? 1))

        CabinSeatMapView(map: CabinMap(map), selected: selected, maxSeats: maxSeats) { seats in
            field.set(.array(seats.map { .string($0) }))
        }
    }
}

struct CabinMap {
    struct Cell: Hashable {
        let id: String?
        let isSeat: Bool
        let available: Bool
        let price: Double
    }

    struct Row: Identifiable {
        let id: String
        let sections: [[Cell]]
    }

    let available: Bool
    let message: String
    let currency: String
    let columns: [String]
    let rows: [Row]

    init(_ v: OpenUIValue?) {
        available = v?["available"]?.boolValue ?? false
        message = v?["message"]?.stringValue ?? ""
        currency = v?["currency"]?.stringValue ?? "USD"
        columns = v?["columns"]?.arrayValue?.compactMap(\.stringValue) ?? []
        rows = (v?["rows"]?.arrayValue ?? []).enumerated().map { index, row in
            let sections = (row["sections"]?.arrayValue ?? []).map { section in
                (section.arrayValue ?? []).map { cell in
                    Cell(id: cell["id"]?.stringValue, isSeat: cell["type"]?.stringValue == "seat",
                         available: cell["available"]?.boolValue ?? false, price: cell["price"]?.numberValue ?? 0)
                }
            }
            return Row(id: row["label"]?.stringValue.flatMap { $0.isEmpty ? nil : $0 } ?? "\(index)", sections: sections)
        }
    }
}

struct CabinSeatMapView: View {
    let map: CabinMap
    let selected: [String]
    let maxSeats: Int
    let onChange: ([String]) -> Void

    private let seatSize: CGFloat = 26

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !map.available || map.rows.isEmpty {
                Label(map.message.isEmpty ? "Pick a flight to choose seats." : map.message, systemImage: "carseat.right")
                    .font(.subheadline).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
            } else {
                header
                ScrollView(.vertical) {
                    VStack(spacing: 6) {
                        ForEach(map.rows) { row in
                            rowView(row)
                        }
                    }
                    .padding(.vertical, 6)
                    .frame(maxWidth: .infinity)
                }
                .frame(maxHeight: 300)
                .background(
                    // A fuselage outline behind the cabin.
                    RoundedRectangle(cornerRadius: 40).fill(Color(.systemBackground))
                )
                legend
                Text(selected.isEmpty ? "Tap \(maxSeats) seat\(maxSeats == 1 ? "" : "s")"
                     : "Selected: \(selected.joined(separator: ", "))")
                    .font(.footnote.weight(.medium))
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private var header: some View {
        HStack(spacing: 4) {
            ForEach(map.columns, id: \.self) { col in
                Text(col).font(.caption2.weight(.bold)).foregroundStyle(.secondary).frame(width: seatSize)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func rowView(_ row: CabinMap.Row) -> some View {
        HStack(spacing: 4) {
            ForEach(Array(row.sections.enumerated()), id: \.offset) { index, section in
                if index > 0 {
                    Text(row.id).font(.caption2).foregroundStyle(.tertiary).frame(width: 20)
                }
                ForEach(Array(section.enumerated()), id: \.offset) { _, cell in
                    seat(cell)
                }
            }
        }
    }

    @ViewBuilder private func seat(_ cell: CabinMap.Cell) -> some View {
        if cell.isSeat, let id = cell.id {
            let isSelected = selected.contains(id)
            Button {
                toggle(id)
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: 6)
                        .fill(isSelected ? Color.accentColor : cell.available
                              ? (cell.price > 0 ? Color.orange.opacity(0.25) : Color.accentColor.opacity(0.18))
                              : Color(.systemGray5))
                    if isSelected {
                        Image(systemName: "checkmark").font(.caption2.weight(.bold)).foregroundStyle(.white)
                    } else if !cell.available {
                        Image(systemName: "xmark").font(.system(size: 8)).foregroundStyle(Color(.systemGray3))
                    }
                }
                .frame(width: seatSize, height: seatSize)
            }
            .buttonStyle(.plain)
            .disabled(!cell.available)
            .accessibilityLabel("Seat \(id)\(cell.price > 0 ? ", extra" : "")")
        } else {
            Color.clear.frame(width: seatSize, height: seatSize)
        }
    }

    private var legend: some View {
        HStack(spacing: 12) {
            legendItem(Color.accentColor.opacity(0.18), "Included")
            legendItem(Color.orange.opacity(0.25), "Extra legroom / paid")
            legendItem(Color(.systemGray5), "Taken")
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
    }

    private func legendItem(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 3).fill(color).frame(width: 10, height: 10)
            Text(text).fixedSize()
        }
    }

    private func toggle(_ id: String) {
        var current = selected
        if let i = current.firstIndex(of: id) {
            current.remove(at: i)
        } else {
            current.append(id)
            if current.count > maxSeats { current.removeFirst(current.count - maxSeats) }
        }
        UISelectionFeedbackGenerator().selectionChanged()
        onChange(current)
    }
}
