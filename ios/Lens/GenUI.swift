import Charts
import SwiftUI

/// Native renderer for the backend's generative-UI catalog (backend/app/schemas.py).
/// The model picks components; SwiftUI draws them. Unknown types are skipped, so the
/// backend can add components without breaking older app builds.
struct GenScreenView: View {
    let screen: GenScreen

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(screen.title)
                .font(.title2.bold())
            ForEach(screen.components) { component in
                GenComponentView(component: component)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct GenComponentView: View {
    let component: GenComponent
    @Environment(\.openURL) private var openURL

    var body: some View {
        switch component.type {
        case "header":
            VStack(alignment: .leading, spacing: 2) {
                if let t = component.title { Text(t).font(.headline) }
                if let s = component.subtitle { Text(s).font(.subheadline).foregroundStyle(.secondary) }
            }
        case "text":
            if let b = component.body ?? component.title { Text(b).font(.body) }
        case "card":
            card
        case "list":
            section {
                ForEach(component.items ?? [], id: \.self) { item in row(item) }
            }
        case "timeline":
            section { timeline }
        case "person":
            person
        case "chips":
            section {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(component.items ?? [], id: \.self) { item in
                            Text(item.title)
                                .font(.subheadline)
                                .padding(.horizontal, 12).padding(.vertical, 6)
                                .background(Color.accentColor.opacity(0.12), in: Capsule())
                        }
                    }
                }
            }
        case "bar_chart":
            section {
                Chart(component.bars ?? [], id: \.self) { bar in
                    BarMark(x: .value("Value", bar.value), y: .value("Label", bar.label))
                        .annotation(position: .trailing) {
                            Text(bar.value, format: .number.precision(.fractionLength(0...1)))
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                }
                .chartXAxis(.hidden)
                .frame(height: CGFloat(max(1, component.bars?.count ?? 1)) * 34 + 10)
            }
        case "link_button":
            if let url = component.url.flatMap(URL.init(string:)) {
                Button { openURL(url) } label: {
                    Label(component.title ?? "Open", systemImage: "arrow.up.right.square")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
            }
        default:
            EmptyView()
        }
    }

    // MARK: - Pieces

    @ViewBuilder
    private func section<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let t = component.title { Text(t).font(.headline) }
            if let s = component.subtitle { Text(s).font(.caption).foregroundStyle(.secondary) }
            content()
        }
    }

    private var card: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let t = component.title { Text(t).font(.headline) }
            if let s = component.subtitle { Text(s).font(.caption).foregroundStyle(.secondary) }
            if let b = component.body { Text(b).font(.subheadline) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 14))
        .contentShape(Rectangle())
        .onTapGesture { open(component.url) }
    }

    private func row(_ item: GenItem) -> some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title).font(.subheadline.weight(.medium)).lineLimit(2)
                if let s = item.subtitle { Text(s).font(.caption).foregroundStyle(.secondary) }
            }
            Spacer()
            if let m = item.meta { Text(m).font(.caption2).foregroundStyle(.secondary) }
            if item.url != nil { Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary) }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .onTapGesture { open(item.url) }
    }

    private var timeline: some View {
        let items = component.items ?? []
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                HStack(alignment: .top, spacing: 12) {
                    VStack(spacing: 0) {
                        Circle().fill(Color.accentColor).frame(width: 10, height: 10).padding(.top, 5)
                        if index < items.count - 1 {
                            Rectangle().fill(Color.accentColor.opacity(0.3)).frame(width: 2)
                        }
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        if let m = item.meta { Text(m).font(.caption2).foregroundStyle(.secondary) }
                        Text(item.title).font(.subheadline.weight(.medium)).lineLimit(2)
                        if let s = item.subtitle { Text(s).font(.caption).foregroundStyle(.secondary) }
                    }
                    .padding(.bottom, 14)
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
                .onTapGesture { open(item.url) }
            }
        }
    }

    private var person: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Text(initials(component.title ?? "?"))
                    .font(.headline)
                    .frame(width: 48, height: 48)
                    .background(Color.accentColor.opacity(0.18), in: Circle())
                VStack(alignment: .leading) {
                    Text(component.title ?? "").font(.headline)
                    if let s = component.subtitle { Text(s).font(.caption).foregroundStyle(.secondary) }
                }
                Spacer()
                if component.url != nil {
                    Image(systemName: "arrow.up.right").foregroundStyle(.secondary)
                }
            }
            .contentShape(Rectangle())
            .onTapGesture { open(component.url) }
            if let b = component.body { Text(b).font(.subheadline) }
            ForEach(component.items ?? [], id: \.self) { item in row(item) }
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 14))
    }

    private func initials(_ name: String) -> String {
        let cleaned = name.replacingOccurrences(of: "@", with: "")
        let parts = cleaned.split(separator: " ").prefix(2)
        return parts.compactMap { $0.first.map(String.init) }.joined().uppercased()
    }

    private func open(_ urlString: String?) {
        if let urlString, let url = URL(string: urlString) { openURL(url) }
    }
}
