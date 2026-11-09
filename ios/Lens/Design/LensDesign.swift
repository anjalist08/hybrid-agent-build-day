import OpenUI
import SwiftUI

/// Design tokens and shared pieces for the "calm assistant" look: white canvas, light-gray
/// assistant surfaces, black user bubbles, one blue pill action per card.
enum LensDesign {
    static let blue = Color(red: 0.0, green: 0.48, blue: 1.0)          // #007AFF
    static let blueSoft = Color(red: 0.0, green: 0.48, blue: 1.0).opacity(0.10)
    static let surface = Color(red: 0.949, green: 0.949, blue: 0.969)   // #F2F2F7
    static let secondaryFill = Color(red: 0.933, green: 0.933, blue: 0.937)
    static let ink = Color(red: 0.11, green: 0.11, blue: 0.118)         // #1C1C1E
    static let muted = Color(red: 0.43, green: 0.43, blue: 0.45)        // #6E6E73
    static let hairline = Color(red: 0.898, green: 0.898, blue: 0.918)  // #E5E5EA
    static let bubbleRadius: CGFloat = 22

    /// OpenUI's built-in components, tuned to the same tokens.
    static var openUITheme: OpenUITheme {
        var theme = OpenUITheme()
        theme.colors.accent = blue
        theme.colors.surface = .white
        theme.colors.textSecondary = muted
        theme.colors.border = hairline
        theme.colors.info = blue
        theme.radius.medium = 14
        theme.radius.large = 18
        theme.fonts.title = .headline
        theme.fonts.heading = .headline
        return theme
    }
}

// MARK: - Buttons

struct PillButtonStyle: ButtonStyle {
    var prominent = true
    var fullWidth = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body)
            .foregroundStyle(prominent ? Color.white : LensDesign.ink)
            .padding(.horizontal, 20)
            .frame(minHeight: 50)
            .frame(maxWidth: fullWidth ? .infinity : nil)
            .background(prominent ? LensDesign.blue : LensDesign.secondaryFill, in: Capsule())
            .opacity(configuration.isPressed ? 0.75 : 1)
    }
}

// MARK: - Navigation

/// "‹ Home · Visit Mia"
struct Breadcrumb: View {
    let title: String?
    let onBack: () -> Void

    var body: some View {
        Button(action: onBack) {
            HStack(spacing: 4) {
                Image(systemName: "chevron.left").font(.system(size: 15, weight: .medium))
                Text(title.map { "Home · \($0)" } ?? "Home")
            }
            .font(.body)
            .foregroundStyle(LensDesign.blue)
        }
        .buttonStyle(.plain)
    }
}

/// Dots on a hairline with labels; the current step is blue.
struct StepTracker: View {
    let steps: [String]
    let current: Int

    var body: some View {
        // Equal flexible columns so all steps always fit the screen; future steps keep their space hidden.
        HStack(alignment: .top, spacing: 0) {
            ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                VStack(alignment: .leading, spacing: 10) {
                    ZStack(alignment: .leading) {
                        Rectangle().fill(LensDesign.hairline).frame(height: 2)
                        Circle()
                            .fill(index == current ? LensDesign.blue : Color(.systemGray3))
                            .frame(width: 8, height: 8)
                    }
                    .frame(height: 8)
                    Text(step)
                        .font(.footnote)
                        .foregroundStyle(index == current ? LensDesign.blue : LensDesign.muted)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                }
                .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
                .opacity(index <= current ? 1 : 0)
            }
        }
        .animation(.easeInOut(duration: 0.25), value: current)
    }
}

// MARK: - Composer

/// Capsule "Message" field with a round blue send button.
struct Composer: View {
    @Binding var text: String
    var placeholder = "Message"
    var disabled = false
    let onSend: () -> Void
    @FocusState private var focused: Bool

    private var canSend: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !disabled }

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField(placeholder, text: $text, axis: .vertical)
                .lineLimit(1...5)
                .focused($focused)
                .padding(.leading, 16)
                .padding(.vertical, 13)
                .onSubmit { if canSend { send() } }
            Button(action: send) {
                Image(systemName: "arrow.up")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(canSend ? LensDesign.blue : LensDesign.blue.opacity(0.3), in: Circle())
            }
            .disabled(!canSend)
            .padding(5)
            .accessibilityLabel("Send")
        }
        .background(Capsule().stroke(LensDesign.hairline, lineWidth: 1).background(Capsule().fill(.white)))
    }

    private func send() {
        focused = false
        onSend()
    }
}

// MARK: - Bubbles

struct AssistantBubble<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .font(.body)
            .foregroundStyle(LensDesign.ink)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(LensDesign.surface, in: RoundedRectangle(cornerRadius: LensDesign.bubbleRadius, style: .continuous))
            .frame(maxWidth: 330, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct UserBubble: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.body)
            .foregroundStyle(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(LensDesign.ink, in: RoundedRectangle(cornerRadius: LensDesign.bubbleRadius, style: .continuous))
            .frame(maxWidth: 300, alignment: .trailing)
            .frame(maxWidth: .infinity, alignment: .trailing)
    }
}

/// The agent's OpenUI `Card`, restyled as the design's light-gray card with no border.
struct LensCardView: View {
    let context: ComponentContext

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            context.render(prop: "children")
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LensDesign.surface, in: RoundedRectangle(cornerRadius: LensDesign.bubbleRadius, style: .continuous))
    }
}

/// Home wallpaper: soft, colorful light — blue and indigo with warm pink and amber glows.
struct LensWallpaper: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.16, green: 0.45, blue: 0.98), Color(red: 0.36, green: 0.24, blue: 0.86)],
                           startPoint: .top, endPoint: .bottom)
            GeometryReader { geo in
                let w = geo.size.width, h = geo.size.height
                ZStack {
                    Circle().fill(Color(red: 1.0, green: 0.42, blue: 0.62)).frame(width: w * 1.1)
                        .position(x: w * 0.95, y: h * 0.62).opacity(0.75)
                    Circle().fill(Color(red: 1.0, green: 0.72, blue: 0.30)).frame(width: w * 0.9)
                        .position(x: w * 0.05, y: h * 0.92).opacity(0.70)
                    Circle().fill(Color(red: 0.25, green: 0.85, blue: 0.95)).frame(width: w * 0.9)
                        .position(x: w * 0.0, y: h * 0.18).opacity(0.55)
                    Circle().fill(Color(red: 0.55, green: 0.35, blue: 1.0)).frame(width: w * 0.8)
                        .position(x: w * 0.85, y: h * 0.05).opacity(0.6)
                }
                .blur(radius: 90)
            }
        }
    }
}
