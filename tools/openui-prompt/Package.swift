// swift-tools-version:6.0
// Generates backend/app/openui/system-prompt.md from the OpenUI chat library plus Lens's
// SeatMap component and ticket tools.   Run:  cd tools/openui-prompt && swift run
import PackageDescription

let package = Package(
    name: "LensPrompt",
    platforms: [.macOS(.v14)],
    dependencies: [
        // Pinned: the repo has a single commit and no releases.
        .package(url: "https://github.com/martinmitrevski/OpenUI.git", revision: "5979833d5793aabd3df6466f1395125c62a4f87a"),
    ],
    targets: [
        .executableTarget(name: "LensPrompt", dependencies: [.product(name: "OpenUI", package: "OpenUI")]),
    ]
)
