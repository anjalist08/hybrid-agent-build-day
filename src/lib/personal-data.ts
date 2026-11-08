export type Message = {
  id: string;
  from: "Mia" | "You";
  app: "iMessage" | "Gmail" | "WhatsApp";
  date: string;
  text: string;
};

// Mock on-device message history with Mia.
export const MESSAGES: Message[] = [
  { id: "m1", from: "Mia", app: "iMessage", date: "Oct 2", text: "Weeknights are rough for me, I'm never out of work before 6:30." },
  { id: "m2", from: "Mia", app: "iMessage", date: "Oct 9", text: "Fridays after 7 are perfect honestly, that's my reset night." },
  { id: "m3", from: "You", app: "iMessage", date: "Oct 9", text: "Noted! Dinner before shows or after?" },
  { id: "m4", from: "Mia", app: "iMessage", date: "Oct 9", text: "Before! I get hangry at concerts lol. Somewhere near the venue." },
  { id: "m5", from: "Mia", app: "Gmail", date: "Oct 15", text: "I'm away Saturday the 14th for my sister's thing in Sacramento." },
  { id: "m6", from: "Mia", app: "WhatsApp", date: "Oct 21", text: "Please no standing GA again, my feet were dead after the last one 😅 seats please." },
  { id: "m7", from: "Mia", app: "iMessage", date: "Oct 28", text: "Maggie Rogers on repeat this week. Would love to see her live." },
  { id: "m8", from: "Mia", app: "WhatsApp", date: "Nov 3", text: "Sundays I'm usually wiped, early nights only." },
  { id: "m9", from: "Mia", app: "Gmail", date: "Nov 5", text: "Free this Friday the 13th after 6:45 if you want to do something!" },
];

const STOP = new Set("a an the to of for and or is are on in at my me i you what does do find when with about her she mia's mia time good best like prefer".split(" "));

const SYNONYMS: Record<string, string[]> = {
  time: ["friday", "after", "weeknights", "sundays", "free", "night", "early"],
  when: ["friday", "after", "weeknights", "free", "away"],
  seat: ["seats", "standing", "ga"],
  seats: ["seats", "standing", "ga"],
  food: ["dinner", "hangry"],
  dinner: ["dinner", "hangry", "before"],
  free: ["free", "away", "friday"],
  music: ["maggie", "live", "concerts"],
};

export function searchMessages(query: string): Message[] {
  const words = query.toLowerCase().match(/[a-z0-9']+/g) ?? [];
  const terms = new Set<string>();
  for (const w of words) {
    (SYNONYMS[w] ?? []).forEach((s) => terms.add(s));
    if (!STOP.has(w)) terms.add(w);
  }
  if (terms.size === 0) SYNONYMS.time.forEach((s) => terms.add(s));
  return MESSAGES.filter((m) => m.from === "Mia")
    .map((m) => {
      const t = m.text.toLowerCase();
      return { m, score: [...terms].filter((x) => t.includes(x)).length };
    })
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 4)
    .map((r) => r.m);
}

export function summarize(hits: Message[]): string {
  if (!hits.length) return "I couldn't find anything from Mia about that in your messages.";
  const t = hits.map((h) => h.text.toLowerCase()).join(" ");
  const out: string[] = [];
  if (t.includes("friday") || t.includes("free")) out.push("Mia prefers **Friday evenings after 7** and said she's free Fri, Nov 13 after 6:45.");
  if (t.includes("weeknights")) out.push("Weeknights are hard — she's rarely free before 6:30.");
  if (t.includes("away")) out.push("She's away Saturday, Nov 14.");
  if (t.includes("sundays")) out.push("Sundays she wants early nights.");
  if (t.includes("standing") || t.includes("seats")) out.push("She'd rather have **seats than standing GA**.");
  if (t.includes("dinner") || t.includes("hangry")) out.push("She likes **dinner before** the show, near the venue.");
  if (t.includes("maggie")) out.push("She's been listening to Maggie Rogers a lot.");
  if (!out.length) out.push(`Mia mentioned: "${hits[0].text}"`);
  return out.join(" ");
}
