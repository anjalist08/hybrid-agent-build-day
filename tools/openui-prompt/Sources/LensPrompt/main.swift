import Foundation
import OpenUI

// Writes backend/app/openui/system-prompt.md: the OpenUI chat library, Lens's SeatMap
// component and the ticket tools from backend/app/openui/tools.json. Every example must
// parse cleanly or nothing is written (a broken example teaches the model broken UI).
//
//   cd tools/openui-prompt && swift run

let repo = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().deletingLastPathComponent()
let openuiDir = repo.appendingPathComponent("backend/app/openui")

// Keep in sync with ios/Lens/Agent/LensComponents.swift.
let seatMap = ComponentSchema(
    "SeatMap",
    description: "Interactive seat map of a venue. Tap free seats to select them; held and booked seats are greyed out. "
        + "Pass the whole get_seats Query result as `seats`, bind `selected` to a $variable holding the chosen seat ids "
        + "(string[]), and cap the selection with maxSeats.",
    props: [
        .required("seats", .any),
        .binding("selected", .array(.string)),
        .optional("maxSeats", .number),
    ]
)

let library = ComponentLibrary.openUIChat.addingContent(
    [ComponentDefinition(seatMap, renderer: nil)],
    group: "Ticketing",
    notes: [
        "SeatMap renders the seats natively; never list individual seats in a Table instead.",
        "Show the running selection next to the map, e.g. TextContent(@Count($selected) + \" selected: \" + $selected).",
    ]
)

let preamble = """
You are Lens, a personal assistant inside the user's iPhone app. People forward you things their friends sent \
them — a message, an email, a link — about a concert or show. Work out which event it is, then build an \
interactive UI with OpenUI Lang so they can pick seats, hold them and check out without leaving the chat.
"""

let rules = [
    "Before writing UI for an event, call the find_event tool with the user's text to get the event id. Never guess an event id.",
    "If find_event returns no good match (match_score 0), say you couldn't find tickets for it and list the events you do have with a FollowUpBlock.",
    "Use the event id from find_event in every get_event, get_seats, hold_seats and book_seats call.",
    "Put the whole purchase in ONE Card: event header and details, price tiers, SeatMap, a hold button, then checkout and confirmation that appear via ternaries on the mutations' status.",
    "Seats must be held (hold_seats) before checkout; book_seats takes hold.data.hold_token.",
    "Payment is a demo: ask only for name and email, never card numbers. Say 'Demo payment — no card is charged' near the pay button.",
    "Mention the friend by name if their message includes one, e.g. 'Alex sent you this'.",
]

let example = #"""
Example — a friend's message about a concert. find_event returned id "midnight-static-sf"; the Query defaults are condensed real results:

```openui-lang
root = Card([header, intro, facts, tiers, pickHeader, seatMap, selection, holdButtons, holdError, checkout, done, followUps])
header = CardHeader("Midnight Static — The Neon Tide Tour", "Sat Dec 12 · The Fillmore, San Francisco · Doors 7:00 PM")
intro = TextContent("Alex sent you this one. " + event.description)
event = Query("get_event", {event_id: "midnight-static-sf"}, {id: "midnight-static-sf", name: "", artist: "", venue: "", city: "", date: "", doors: "", description: "", seats_available: 0, price_tiers: []})
facts = EntityList([{left: "Seats left", right: "" + event.seats_available, rightVariant: "number"}, {left: "Doors", right: event.doors}])
tiers = Table([Col("Section", event.price_tiers.label), Col("Price", event.price_tiers.price, "number"), Col("Left", event.price_tiers.available, "number")])
pickHeader = InlineHeader("Pick your seats", "Up to 4 seats. Stage is at the top.")
$selected = []
seats = Query("get_seats", {event_id: "midnight-static-sf"}, {event_id: "midnight-static-sf", width: 0, height: 0, stage: "top", categories: [], seats: []})
seatMap = SeatMap(seats, $selected, 4)
selection = TextContent(@Count($selected) == 0 ? "Tap seats on the map to select them." : @Count($selected) + " selected: " + $selected)
hold = Mutation("hold_seats", {event_id: "midnight-static-sf", seats: $selected})
holdButtons = Buttons([Button("Hold seats", Action([@Run(hold), @Run(seats)]), "primary")])
holdError = hold.status == "error" ? Callout("error", "Couldn't hold those seats", "" + hold.error) : null
checkout = hold.status == "success" ? checkoutForm : null
checkoutForm = Form("checkout", payButtons, [nameField, emailField])
nameField = FormControl("Name", Input("name", "Your name", "text", {required: true}, $name))
emailField = FormControl("Email", Input("email", "you@example.com", "email", {required: true, email: true}, $email), "Demo payment — no card is charged. Seats held for 10 minutes.")
$name = ""
$email = ""
book = Mutation("book_seats", {event_id: "midnight-static-sf", hold_token: hold.data.hold_token, name: $name, email: $email})
payButtons = Buttons([Button("Pay $" + hold.data.total, Action([@Run(book), @Run(seats), @ToAssistant("I booked the tickets")]), "primary")])
done = book.status == "success" ? Callout("success", "You're going!", "Order " + book.data.order_id + " · " + book.data.message) : null
followUps = FollowUpBlock([FollowUpItem("What's the venue like?"), FollowUpItem("Tell Alex I got tickets")])
```
"""#

// Tools: the four app-side tools from tools.json (used in Query/Mutation), plus find_event,
// which only the model calls on the server before writing UI.
let toolsJSON = try OpenUIJSON.parse(Data(contentsOf: openuiDir.appendingPathComponent("tools.json")))
let tools: [ToolDescriptor] = (toolsJSON.arrayValue ?? []).map { t in
    .spec(ToolSpec(name: t["name"]?.stringValue ?? "", description: t["description"]?.stringValue,
                   inputSchema: t["inputSchema"] ?? [:], outputSchema: t["outputSchema"] ?? [:]))
}

var broken: [String] = []
for program in example.components(separatedBy: "```openui-lang\n").dropFirst() {
    let code = program.components(separatedBy: "\n```").first ?? program
    let result = library.parser.parse(code)
    broken += result.meta.errors.map { "error: \($0.message)" }
    broken += result.meta.unresolved.map { "unresolved: \($0)" }
    broken += result.meta.orphaned.map { "orphaned: \($0)" }
    if result.root == nil { broken.append("nothing renders") }
}
guard broken.isEmpty else {
    FileHandle.standardError.write(Data(("Example does not parse:\n" + broken.joined(separator: "\n") + "\n").utf8))
    exit(1)
}

var options = library.defaultPromptOptions
options.preamble = preamble
options.additionalRules += rules
options.toolExamples = [example]
options.tools = tools

let out = openuiDir.appendingPathComponent("system-prompt.md")
try library.systemPrompt(options).write(to: out, atomically: true, encoding: .utf8)
print("Wrote \(out.path)")
