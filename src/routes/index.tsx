import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft, RotateCcw, Mic, Keyboard, Check, Ticket, Search, MessageSquare, Mail,
  CalendarDays, Lock, Send, ArrowUpRight,
} from "lucide-react";
import concert from "@/assets/concert.jpg";
import { searchMessages, summarize, type Message } from "@/lib/personal-data";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Friday Plan — personal assistant prototype" },
      { name: "description", content: "Plan a concert night and find a time that works by searching your own message history." },
      { property: "og:title", content: "Friday Plan — personal assistant prototype" },
      { property: "og:description", content: "Plan a concert night and find a time that works using your own messages." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

type Step = "lock" | "suggest" | "searching" | "options" | "mia" | "invite" | "remember" | "plan";
type ChatItem = { role: "user" | "assistant"; text: string; hits?: Message[]; searching?: boolean };

const OPTIONS = [
  { price: 65, label: "Standing", sub: "General admission · Floor" },
  { price: 85, label: "Seated", sub: "Reserved balcony · Row J" },
  { price: 95, label: "Seated, Better View", sub: "Reserved loge · Row C · Center" },
];

function Index() {
  const [step, setStep] = useState<Step>("lock");
  const [seat, setSeat] = useState(1);
  const [chat, setChat] = useState<ChatItem[]>([]);
  const [chatOpen, setChatOpen] = useState(false);

  const ask = (q: string) => {
    setChatOpen(true);
    setChat((c) => [...c, { role: "user", text: q }, { role: "assistant", text: "", searching: true }]);
    setTimeout(() => {
      const hits = searchMessages(q);
      setChat((c) => [...c.slice(0, -1), { role: "assistant", text: summarize(hits), hits }]);
    }, 1100);
  };

  const restart = () => { setStep("lock"); setChat([]); setChatOpen(false); };

  return (
    <main className="min-h-screen bg-canvas flex items-center justify-center p-6">
      <div className="relative w-[390px] h-[800px] rounded-[48px] bg-background shadow-2xl overflow-hidden border-[10px] border-primary flex flex-col">
        <StatusBar dark={step === "lock"} />
        {step === "lock" ? (
          <LockScreen onOpen={() => setStep("suggest")} />
        ) : (
          <>
            <div className="flex items-center justify-between px-6 pt-2 text-xs text-muted-foreground">
              <button className="flex items-center gap-1" onClick={() => (chatOpen ? setChatOpen(false) : setStep("suggest"))}>
                <ChevronLeft className="size-3.5" /> {chatOpen ? "Back" : "Suggestions"}
              </button>
              <button className="flex items-center gap-1" onClick={restart}><RotateCcw className="size-3" /> Restart</button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 pt-5 pb-4">
              {chatOpen ? (
                <ChatView chat={chat} onBack={() => { setChatOpen(false); setStep("options"); }} />
              ) : (
                <div key={step} className="animate-fade-up">
                  {step === "suggest" && <Suggest onNext={() => setStep("searching")} />}
                  {step === "searching" && <Searching onNext={() => setStep("options")} />}
                  {step === "options" && <Options seat={seat} setSeat={setSeat} onNext={() => setStep("mia")} />}
                  {step === "mia" && <MiaTime onNext={() => setStep("invite")} />}
                  {step === "invite" && <Invite seat={seat} onNext={() => setStep("remember")} />}
                  {step === "remember" && <Remember onNext={() => setStep("plan")} />}
                  {step === "plan" && <Plan seat={seat} onRestart={restart} />}
                </div>
              )}
            </div>
            <Composer onSend={ask} />
          </>
        )}
      </div>
    </main>
  );
}

function StatusBar({ dark }: { dark?: boolean }) {
  return (
    <div className={`flex items-center justify-between px-7 pt-3 pb-1 text-xs font-semibold ${dark ? "bg-primary text-primary-foreground" : ""}`}>
      <span>9:41</span>
      <span className="h-6 w-24 rounded-full bg-primary" />
      <span>●●● ▮</span>
    </div>
  );
}

function LockScreen({ onOpen }: { onOpen: () => void }) {
  const card = "border-t border-primary-foreground/15 py-4 text-sm";
  return (
    <div className="flex-1 bg-primary text-primary-foreground px-6 pt-8">
      <p className="text-xs opacity-60">Good morning</p>
      <p className="text-6xl font-light mt-1">9:41</p>
      <p className="text-xs opacity-60 mt-1 mb-8">Thursday, November 12</p>
      <div className={card}>
        <p className="text-xs opacity-60 mb-1">Friday night</p>
        <p>Your favorite artist is playing Friday, and your calendar is clear. Interested?</p>
        <button onClick={onOpen} className="mt-3 text-xs font-semibold underline underline-offset-4">Take a look</button>
      </div>
      <div className={card}>
        <p className="text-xs opacity-60 mb-1">Commute</p>
        <p className="opacity-80">Rain expected at 10 am. Leave by 9:50?</p>
      </div>
    </div>
  );
}

function Title({ h, sub }: { h: string; sub: string }) {
  return (<><h1 className="text-[28px] leading-tight font-bold tracking-tight">{h}</h1><p className="text-xs text-muted-foreground mt-1 mb-5">{sub}</p></>);
}
function Primary(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className="w-full rounded-full bg-primary text-primary-foreground py-3.5 text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-40" />;
}
function EventCard() {
  return (
    <div className="flex items-center gap-3 rounded-2xl border p-3 mb-4">
      <div className="rounded-lg bg-secondary px-2 py-1 text-center"><p className="text-[9px] text-muted-foreground">NOV</p><p className="text-lg font-bold leading-none">13</p></div>
      <div><p className="text-sm font-semibold">Maggie Rogers</p><p className="text-xs text-muted-foreground">Fri, Nov 13 · 8 PM · Fox Theater</p></div>
    </div>
  );
}

function Suggest({ onNext }: { onNext: () => void }) {
  return (
    <>
      <Title h="Friday sounds good." sub="A little room in your week. An artist you love." />
      <img src={concert} width={1024} height={640} alt="Concert stage" className="rounded-2xl w-full h-44 object-cover mb-4" />
      <p className="text-lg font-semibold">Maggie Rogers</p>
      <p className="text-xs text-muted-foreground mb-4">Fox Theater · Oakland, CA</p>
      <div className="text-sm divide-y border-y mb-6">
        <div className="flex py-3"><span className="w-20 text-muted-foreground">When</span>Fri, Nov 13 · 8–10:30 PM</div>
        <div className="flex py-3"><span className="w-20 text-muted-foreground">Doors</span>7 PM · All ages</div>
      </div>
      <Primary onClick={onNext}><Ticket className="size-4" /> Find tickets</Primary>
    </>
  );
}

function Searching({ onNext }: { onNext: () => void }) {
  const [done, setDone] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDone(true), 1600); return () => clearTimeout(t); }, []);
  useEffect(() => { if (!done) return undefined; const t = setTimeout(onNext, 500); return () => clearTimeout(t); }, [done, onNext]);
  return (
    <>
      <Title h="Finding your tickets." sub="Searching live listings under $100." />
      <EventCard />
      <div className="flex flex-col items-center py-8">
        <div className={`size-16 rounded-full border-2 ${done ? "border-success" : "border-border border-t-link animate-spin"} flex items-center justify-center`}>
          {done && <Check className="size-6 text-success" />}
        </div>
        <p className="font-semibold mt-5">{done ? "Found 3 options" : "Checking availability & total prices"}</p>
      </div>
      <div className="rounded-2xl border p-4 text-xs mb-6">
        <p className="font-semibold flex items-center gap-1.5"><Check className="size-3.5" /> One-time search approved</p>
        <p className="text-muted-foreground mt-1">Only the event and your budget were shared.</p>
      </div>
      <Primary onClick={onNext} disabled={!done}>Continue</Primary>
    </>
  );
}

function Options({ seat, setSeat, onNext }: { seat: number; setSeat: (n: number) => void; onNext: () => void }) {
  return (
    <>
      <Title h="Three ways to be there." sub="All under $100. All prices include fees." />
      <EventCard />
      <div className="rounded-2xl border divide-y mb-6">
        {OPTIONS.map((o, i) => (
          <button key={o.price} onClick={() => setSeat(i)} className="w-full text-left p-4 flex justify-between items-start">
            <div><p className="text-sm font-semibold">${o.price} — {o.label}</p><p className="text-xs text-muted-foreground">{o.sub}</p></div>
            <span className={`size-4 rounded-full border ${seat === i ? "border-[5px] border-primary" : ""}`} />
          </button>
        ))}
      </div>
      <Primary onClick={onNext}>Continue</Primary>
    </>
  );
}

const MIA_STEPS = [
  { icon: MessageSquare, label: "Searching iMessage for “Mia”" },
  { icon: Mail, label: "Searching Gmail threads with Mia" },
  { icon: CalendarDays, label: "Checking your calendar" },
];

function MiaTime({ onNext }: { onNext: () => void }) {
  const [n, setN] = useState(0);
  useEffect(() => { if (n <= MIA_STEPS.length) { const t = setTimeout(() => setN(n + 1), 700); return () => clearTimeout(t); } return undefined; }, [n]);
  const hits = searchMessages("when is mia free friday seats");
  const done = n > MIA_STEPS.length;
  return (
    <>
      <Title h="Does it work for Mia?" sub="Looking through your messages with Mia, on device." />
      <div className="space-y-2 mb-4">
        {MIA_STEPS.map((s, i) => (
          <div key={s.label} className={`flex items-center gap-2 text-xs ${i < n ? "" : "opacity-30"}`}>
            {i < n ? <Check className="size-3.5 text-success" /> : <s.icon className="size-3.5" />} {s.label}
          </div>
        ))}
      </div>
      {done && (
        <div className="animate-fade-up">
          <Hits hits={hits} />
          <div className="rounded-2xl bg-secondary p-4 text-sm my-4">
            <p className="font-semibold mb-1">Friday at 8 PM fits.</p>
            <p className="text-muted-foreground text-xs">Mia is free after 6:45 on the 13th, prefers Friday nights, and asked for seats over standing. Dinner before at 6:45?</p>
          </div>
          <p className="text-[11px] text-muted-foreground flex gap-1.5 mb-5"><Lock className="size-3 shrink-0" /> Messages were read on this device only. Nothing was sent anywhere.</p>
          <Primary onClick={onNext}>Invite Mia for Friday</Primary>
        </div>
      )}
    </>
  );
}

function Hits({ hits }: { hits: Message[] }) {
  return (
    <div className="rounded-2xl border divide-y">
      {hits.map((h) => (
        <div key={h.id} className="p-3">
          <p className="text-[10px] text-muted-foreground">{h.app} · Mia · {h.date}</p>
          <p className="text-xs mt-0.5">“{h.text}”</p>
        </div>
      ))}
    </div>
  );
}

function Invite({ seat, onNext }: { seat: number; onNext: () => void }) {
  const o = OPTIONS[seat] ?? OPTIONS[1]!;
  return (
    <>
      <Title h="A plan is taking shape." sub="You confirmed both actions." />
      <EventCard />
      <div className="rounded-2xl border divide-y text-xs mb-4">
        <div className="p-4"><p className="font-semibold flex gap-2"><Check className="size-4 text-success" /> Invitation sent</p><p className="text-muted-foreground mt-1">To Mia Chen · “Maggie Rogers Fri? Dinner at 6:45 first 🎶”</p></div>
        <div className="p-4"><p className="font-semibold flex gap-2"><Check className="size-4 text-success" /> Added to Personal calendar</p><p className="text-muted-foreground mt-1">Fri, Nov 13 · 6:45–10:30 PM · Tentative</p></div>
      </div>
      <p className="text-xs text-muted-foreground mb-6">Your ${o.price} seat is still just a plan. No tickets have been purchased.</p>
      <Primary onClick={onNext}>Continue</Primary>
    </>
  );
}

function Remember({ onNext }: { onNext: () => void }) {
  return (
    <>
      <Title h="For next time?" sub="A small preference. Entirely your call." />
      <div className="rounded-2xl bg-secondary p-4 text-xs text-muted-foreground mb-6">
        Remember that Mia prefers Friday nights, seats, and dinner before shows. You can edit or forget this anytime.
      </div>
      <div className="space-y-3"><Primary onClick={onNext}>Remember</Primary>
        <button onClick={onNext} className="w-full rounded-full bg-secondary py-3.5 text-sm font-semibold">Just this time</button></div>
    </>
  );
}

function Plan({ seat, onRestart }: { seat: number; onRestart: () => void }) {
  return (
    <>
      <Title h="Friday, looking good." sub="The plan is saved. The night is still yours." />
      <EventCard />
      <div className="rounded-2xl border divide-y text-sm mb-6">
        {[`$${(OPTIONS[seat] ?? OPTIONS[1]!).price} — ${(OPTIONS[seat] ?? OPTIONS[1]!).label}`, "Dinner with Mia at 6:45", "Mia is invited", "Friday is on your calendar"].map((t) => (
          <p key={t} className="p-3.5">{t}</p>
        ))}
      </div>
      <Primary><ArrowUpRight className="size-4" /> Review ticket listing</Primary>
      <button onClick={onRestart} className="mt-4 text-xs text-muted-foreground w-full">Start over</button>
    </>
  );
}

function ChatView({ chat, onBack }: { chat: ChatItem[]; onBack: () => void }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);
  return (
    <div className="space-y-4">
      <Title h="Ask your messages." sub="Searches your personal history on this device." />
      {chat.map((m, i) =>
        m.role === "user" ? (
          <p key={i} className="ml-auto w-fit max-w-[80%] rounded-2xl bg-primary text-primary-foreground px-4 py-2 text-sm">{m.text}</p>
        ) : m.searching ? (
          <p key={i} className="text-xs text-muted-foreground flex items-center gap-2"><Search className="size-3.5 animate-pulse" /> Searching messages with Mia…</p>
        ) : (
          <div key={i} className="space-y-2 animate-fade-up">
            {m.hits && m.hits.length > 0 && <><p className="text-[11px] text-muted-foreground">Found {m.hits.length} messages</p><Hits hits={m.hits} /></>}
            <p className="text-sm" dangerouslySetInnerHTML={{ __html: m.text.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>") }} />
            {i === chat.length - 1 && (
              <button onClick={onBack} className="rounded-full border px-3 py-1.5 text-xs font-medium flex items-center gap-1.5">
                <Ticket className="size-3.5" /> Back to ticket options
              </button>
            )}
          </div>
        ),
      )}
      <div ref={end} />
    </div>
  );
}

const SUGGESTED = ["When is Mia free this week?", "Does Mia like seats or standing?", "Dinner before or after?"];

function Composer({ onSend }: { onSend: (q: string) => void }) {
  const [v, setV] = useState("");
  const submit = () => { if (v.trim()) { onSend(v.trim()); setV(""); } };
  return (
    <div className="px-5 pb-6 pt-2 border-t">
      <div className="flex gap-1.5 overflow-x-auto pb-2">
        {SUGGESTED.map((s) => (
          <button key={s} onClick={() => onSend(s)} className="shrink-0 rounded-full border px-3 py-1 text-[11px]">{s}</button>
        ))}
      </div>
      <div className="flex gap-2">
        <div className="flex-1 flex items-center gap-2 rounded-full bg-secondary px-4">
          <Keyboard className="size-4 text-muted-foreground" />
          <input value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Ask about Mia's preferences…" className="flex-1 bg-transparent py-2.5 text-sm outline-none" />
        </div>
        <button onClick={submit} aria-label="Send" className="size-10 rounded-full bg-secondary flex items-center justify-center">
          {v ? <Send className="size-4" /> : <Mic className="size-4" />}
        </button>
      </div>
      <p className="text-center text-[10px] text-muted-foreground mt-2">🔒 On device</p>
    </div>
  );
}
