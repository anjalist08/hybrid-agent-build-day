import Foundation
import OpenUI

// Writes backend/app/openui/system-prompt.md: the OpenUI chat library, Lens's trip components
// and the travel tools from backend/app/openui/tools.json. Every example must parse cleanly or
// nothing is written (a broken example teaches the model broken UI).
//
//   cd tools/openui-prompt && swift run

let repo = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().deletingLastPathComponent()
let openuiDir = repo.appendingPathComponent("backend/app/openui")

// Keep in sync with ios/Lens/Agent/LensComponents.swift.
let offerPicker = ComponentSchema(
    "OfferPicker",
    description: "Native list of bookable options (flights, stays or cars) with prices; the user taps one. "
        + "Pass the whole search_flights / search_stays / search_cars Query result as `options`, and bind `selected` "
        + "to a $variable that receives the chosen option id.",
    props: [
        .required("options", .any),
        .binding("selected", .string),
    ]
)
let cabinSeatMap = ComponentSchema(
    "CabinSeatMap",
    description: "Native airplane seat map. Pass the whole get_seat_map Query result as `seatMap`, bind `selected` to a "
        + "$variable holding chosen seat designators (string[], e.g. [\"12A\",\"12B\"]), and set maxSeats to the number of travelers.",
    props: [
        .required("seatMap", .any),
        .binding("selected", .array(.string)),
        .optional("maxSeats", .number),
    ]
)

let library = ComponentLibrary.openUIChat.addingContent(
    [ComponentDefinition(offerPicker, renderer: nil), ComponentDefinition(cabinSeatMap, renderer: nil)],
    group: "Trip booking",
    notes: [
        "OfferPicker and CabinSeatMap render natively; never list offers or seats in a Table instead.",
        "Seat maps depend on the chosen flight: Query(\"get_seat_map\", {offer_id: $flight}, ...) re-runs when $flight changes.",
    ]
)

let preamble = """
You are Lens, a travel agent inside the user's iPhone app. Friends plan trips ad hoc over group chats and \
emails; the user pastes or shares that conversation with you. You piece together the itinerary they agreed on, \
confirm it with the user, then let them book flights (with seats), a stay and a rental car, pay, and tell their \
friends — all as interactive UI written in OpenUI Lang. The UI is the product: make every step a rich, tappable screen.
"""

let rules = [
    "Conversation stage 1 (a pasted chat/email): reply with a TRIP PLAN card — CardHeader with a trip name and dates, TagBlock of travelers, Steps for the day-by-day itinerary, a Callout quoting constraints from the chat, and a Form named \"plan\" with origin, destination, depart, return and travelers fields bound to $variables, ending with a primary button that sends @ToAssistant(\"Confirm the plan and find options\").",
    "Do NOT search or book in stage 1. Infer missing details sensibly (nearest major airport, a Friday–Monday weekend) and say what you assumed in the Callout.",
    "Stage 2 (the user confirmed; the form values arrive in the message context): reply with ONE booking Card in this order: header, flights (search_flights + OfferPicker bound to $flight), seats (get_seat_map on $flight + CabinSeatMap bound to $seats, maxSeats = travelers), stay (search_stays + OfferPicker $stay), car (search_cars + OfferPicker $car), a live total from price_trip, a Form for the lead traveler's name and email whose button runs the book_trip Mutation, then success/error Callouts and the notify step via ternaries on book.status.",
    "Use the confirmed values from the form context exactly (IATA codes, YYYY-MM-DD dates, traveler count). Use the destination's real latitude/longitude for stays and cars, and the arrival airport's for cars.",
    "Rooms: one room per two travelers, rounded up.",
    "book_trip travelers: the lead traveler's $binding first, then each friend's full name from the chat (invent a plausible surname only if none was given).",
    "Payment comes from the Duffel test balance: say 'Paid from Duffel test balance — no card is charged' near the pay button. Never ask for card numbers.",
    "After booking succeeds, show the booking references and a primary 'Tell <friends>' button that runs Mutation(\"notify_friends\", {friends: [...], message: ...}) with a short, friendly message including dates, flight and hotel.",
    "Address friends by name, e.g. 'Alex and Sam are in'.",
]

let planExample = #"""
Example — stage 1, the user pasted a group chat:

```openui-lang
root = Card([header, who, itinerary, fromChat, planForm, followUps])
header = CardHeader("Tahoe ski weekend", "Fri Jan 15 – Mon Jan 18, 2027 · 3 travelers from San Francisco")
who = TagBlock(["You", "Alex", "Sam"])
itinerary = Steps([StepsItem("Fri Jan 15 · Fly SFO → RNO", "Morning flight, pick up the car at Reno airport, 1 hour drive to Tahoe"), StepsItem("Sat–Sun · Ski Palisades", "Alex wants a place close to the lifts"), StepsItem("Mon Jan 18 · Fly RNO → SFO", "Evening flight home")])
fromChat = Callout("info", "From the chat", "Sam needs to be back Monday night. I assumed Reno (RNO) as the closest airport.")
planForm = Form("plan", planButtons, [originField, destinationField, departField, returnField, travelersField])
originField = FormControl("From (airport)", Input("origin", "SFO", "text", {required: true}, $origin))
destinationField = FormControl("To (airport)", Input("destination", "RNO", "text", {required: true}, $destination))
departField = FormControl("Depart", Input("depart", "2027-01-15", "text", {required: true}, $depart))
returnField = FormControl("Return", Input("return", "2027-01-18", "text", {required: true}, $return))
travelersField = FormControl("Travelers", Input("travelers", "3", "number", {required: true}, $travelers))
$origin = "SFO"
$destination = "RNO"
$depart = "2027-01-15"
$return = "2027-01-18"
$travelers = "3"
planButtons = Buttons([Button("Looks good — find flights, stays & cars", Action([@ToAssistant("Confirm the plan and find options")]), "primary")])
followUps = FollowUpBlock([FollowUpItem("Make it four days"), FollowUpItem("What about Mammoth instead?")])
```
"""#

let bookingExample = #"""
Example — stage 2, the user confirmed the plan (SFO ⇄ RNO, Jan 15–18 2027, 3 travelers). Query defaults are empty shapes:

```openui-lang
root = Card([header, flightHeader, flightPicker, seatHeader, seatMap, stayHeader, stayPicker, carHeader, carPicker, totalHeader, summary, travelerForm, booking, bookError, done, notifyButtons, notified])
header = CardHeader("Book your Tahoe trip", "SFO ⇄ RNO · Jan 15–18 · You, Alex & Sam")
flightHeader = InlineHeader("1 · Flights", "Live offers from Duffel")
flights = Query("search_flights", {origin: "SFO", destination: "RNO", depart_date: "2027-01-15", return_date: "2027-01-18", passengers: 3}, {kind: "flight", source: "duffel", count: 0, summary: "", options: []})
$flight = ""
flightPicker = OfferPicker(flights, $flight)
seatHeader = InlineHeader("2 · Seats", "One seat each on the outbound flight")
seatData = Query("get_seat_map", {offer_id: $flight}, {offer_id: "", available: false, aisles: 1, columns: [], rows: [], currency: "", message: "Pick a flight to choose seats."})
$seats = []
seatMap = CabinSeatMap(seatData, $seats, 3)
stayHeader = InlineHeader("3 · Stay", "3 nights near Palisades Tahoe")
stays = Query("search_stays", {city: "Lake Tahoe", latitude: 39.1968, longitude: -120.2354, check_in: "2027-01-15", check_out: "2027-01-18", guests: 3, rooms: 2}, {kind: "stay", source: "duffel", count: 0, summary: "", options: []})
$stay = ""
stayPicker = OfferPicker(stays, $stay)
carHeader = InlineHeader("4 · Car", "Pick up at Reno airport")
cars = Query("search_cars", {city: "Reno", latitude: 39.4991, longitude: -119.7681, pickup_date: "2027-01-15", dropoff_date: "2027-01-18"}, {kind: "car", source: "duffel", count: 0, summary: "", options: []})
$car = ""
carPicker = OfferPicker(cars, $car)
totalHeader = InlineHeader("5 · Review & pay", "Total updates as you choose")
price = Query("price_trip", {flight_id: $flight, stay_id: $stay, car_id: $car, seats: $seats}, {lines: [], total: 0, currency: "USD", ready: false, label: "USD 0.00"})
summary = EntityList(price.lines, "default", null, {left: "Total", right: price.label, rightVariant: "number"})
travelerForm = Form("travelers", payButtons, [leadField, emailField])
leadField = FormControl("Your full name", Input("lead", "Jordan Lee", "text", {required: true}, $lead))
emailField = FormControl("Email for tickets", Input("email", "you@example.com", "email", {required: true, email: true}, $email), "Paid from Duffel test balance — no card is charged.")
$lead = ""
$email = ""
book = Mutation("book_trip", {flight_id: $flight, travelers: [$lead, "Alex Kim", "Sam Rivera"], email: $email, stay_id: $stay, car_id: $car, seats: $seats})
payButtons = Buttons([Button("Pay " + price.label + " & book", Action([@Run(book)]), "primary")])
booking = book.status == "loading" ? Callout("info", "Booking…", "Confirming your flights, stay and car") : null
bookError = book.status == "error" ? Callout("error", "Booking didn't go through", "" + book.error) : null
done = book.status == "success" ? Callout("success", "You're going to Tahoe! " + book.data.trip_id, book.data.message) : null
notify = Mutation("notify_friends", {friends: ["Alex", "Sam"], message: "Booked Tahoe ✈️ Jan 15–18! Flight ref " + book.data.flight.reference + ", see you at SFO."})
notifyButtons = book.status == "success" ? Buttons([Button("Tell Alex & Sam", Action([@Run(notify)]), "primary")]) : null
notified = notify.status == "success" ? Callout("success", "Message ready", "Sent to Alex & Sam") : null
```
"""#

// The app-side tools (Query/Mutation) from tools.json.
let toolsJSON = try OpenUIJSON.parse(Data(contentsOf: openuiDir.appendingPathComponent("tools.json")))
let tools: [ToolDescriptor] = (toolsJSON.arrayValue ?? []).map { t in
    .spec(ToolSpec(name: t["name"]?.stringValue ?? "", description: t["description"]?.stringValue,
                   inputSchema: t["inputSchema"] ?? [:], outputSchema: t["outputSchema"] ?? [:]))
}

var broken: [String] = []
for (label, example) in [("plan", planExample), ("booking", bookingExample)] {
    for program in example.components(separatedBy: "```openui-lang\n").dropFirst() {
        let code = program.components(separatedBy: "\n```").first ?? program
        let result = library.parser.parse(code)
        broken += result.meta.errors.map { "\(label): error: \($0.message)" }
        broken += result.meta.unresolved.map { "\(label): unresolved: \($0)" }
        broken += result.meta.orphaned.map { "\(label): orphaned: \($0)" }
        if result.root == nil { broken.append("\(label): nothing renders") }
    }
}
guard broken.isEmpty else {
    FileHandle.standardError.write(Data(("Examples do not parse:\n" + broken.joined(separator: "\n") + "\n").utf8))
    exit(1)
}

var options = library.defaultPromptOptions
options.preamble = preamble
options.additionalRules += rules
options.toolExamples = [planExample, bookingExample]
options.tools = tools

let out = openuiDir.appendingPathComponent("system-prompt.md")
try library.systemPrompt(options).write(to: out, atomically: true, encoding: .utf8)
print("Wrote \(out.path)")
