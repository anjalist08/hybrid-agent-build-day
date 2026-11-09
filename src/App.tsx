import { useState } from "react";
import { ActionButton, Composer, Toggle, type ButtonTone } from "./components/MiaSystem";

type Screen =
  | "home"
  | "permission"
  | "settings"
  | "ready"
  | "availability"
  | "flights"
  | "review"
  | "confirmation";

type AccessKey = "Messages" | "Mail" | "WhatsApp" | "Calendar" | "Photos" | "Spotify";

const accessDescriptions: Record<AccessKey, string> = {
  Messages: "Conversations and shared plans",
  Mail: "Emails and reservations",
  WhatsApp: "Chats and preferences",
  Calendar: "Events and availability",
  Photos: "Photos you choose to share",
  Spotify: "Listening history and favorites",
};

const initialAccess: Record<AccessKey, boolean> = {
  Messages: false,
  Mail: false,
  WhatsApp: false,
  Calendar: false,
  Photos: false,
  Spotify: false,
};

function Nav({ onHome, detail = "Visit Mia" }: { onHome: () => void; detail?: string }) {
  return (
    <div className="nav">
      <ActionButton
        label={detail ? `‹ Home · ${detail}` : "‹ Home"}
        tone="quiet"
        onClick={onHome}
        className="nav-action"
      />
    </div>
  );
}

function Suggestion({
  category,
  time,
  body,
  action,
  onAction,
  dismiss,
}: {
  category: string;
  time: string;
  body: string;
  action: string;
  onAction: () => void;
  dismiss?: () => void;
}) {
  return (
    <div className="suggestion">
      <div className="suggestion-meta">
        <span>{category}</span>
        <span>{time}</span>
      </div>
      <div className="suggestion-copy">{body}</div>
      <div className="suggestion-actions">
        <ActionButton label={action} tone="quiet" onClick={onAction} />
        {dismiss ? <ActionButton label="Not now" tone="muted" onClick={dismiss} /> : null}
      </div>
    </div>
  );
}

function Home({
  onVisit,
  onSettings,
  onAsk,
}: {
  onVisit: () => void;
  onSettings: () => void;
  onAsk: () => void;
}) {
  const [visitVisible, setVisitVisible] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <main className="home">
      <section className="greeting">
        <div className="date">Thursday, November 12</div>
        <div className="clock">9:41</div>
        <div className="morning">Good morning</div>
      </section>

      <section className="suggestion-feed">
        {visitVisible ? (
          <Suggestion
            category="Visit Mia"
            time="now"
            body="Visit Mia in New York? Check her dates and find a flight."
            action="Take a look"
            onAction={onVisit}
            dismiss={() => setVisitVisible(false)}
          />
        ) : null}
        <Suggestion
          category="Commute"
          time="8 min ago"
          body="Rain expected at 10 am. Your usual route adds 12 min — leave by 9:50?"
          action="See route"
          onAction={() =>
            setNotice("Rain is expected at 10 am. Aim to leave by 9:50 and allow 12 extra minutes.")
          }
        />
        <Suggestion
          category="Reading"
          time="saved Tuesday"
          body="You saved an article on flow states. 6 min read — quiet morning to catch up."
          action="Open article"
          onAction={() => setNotice("The saved article is not connected in this prototype.")}
        />
      </section>

      <div className="home-actions">
        <ActionButton label="Settings" tone="muted" onClick={onSettings} />
        <ActionButton label="Ask" tone="soft" onClick={onAsk} />
      </div>

      {notice ? (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Information">
          <div className="overlay-card">
            <div className="title">For you</div>
            <div className="body">{notice}</div>
            <ActionButton label="Done" tone="primary" onClick={() => setNotice(null)} full />
          </div>
        </div>
      ) : null}
    </main>
  );
}

function Permission({
  onHome,
  onAllow,
  onContinue,
}: {
  onHome: () => void;
  onAllow: () => void;
  onContinue: () => void;
}) {
  return (
    <main className="screen">
      <Nav onHome={onHome} detail="" />
      <section className="page-content">
        <div className="page-heading">
          <div className="title">Use your shared messages?</div>
          <div className="subheadline">Read only the dates Mia has shared with you.</div>
        </div>
        <div className="surface permission-card">
          <div className="headline">Messages access is off</div>
          <div className="body">
            Allow your on-device AI to use your message history. Your conversations stay on this
            device.
          </div>
          <div className="footnote">You can turn this off in Settings anytime.</div>
        </div>
      </section>
      <div className="bottom-actions">
        <ActionButton label="Allow Messages" tone="primary" onClick={onAllow} full />
        <ActionButton label="Continue without access" tone="secondary" onClick={onContinue} full />
      </div>
    </main>
  );
}

function Settings({
  access,
  setAccess,
  onHome,
}: {
  access: Record<AccessKey, boolean>;
  setAccess: (next: Record<AccessKey, boolean>) => void;
  onHome: () => void;
}) {
  const keys = Object.keys(access) as AccessKey[];

  return (
    <main className="screen">
      <Nav onHome={onHome} detail="" />
      <section className="page-content settings-content">
        <div className="page-heading">
          <div className="title">App access</div>
          <div className="subheadline">Choose what your on-device AI can use.</div>
        </div>
        <div className="surface access-list">
          {keys.map((key) => (
            <div className="access-row" key={key}>
              <div className="access-copy">
                <div className="body">{key}</div>
                <div className="footnote">{accessDescriptions[key]}</div>
              </div>
              <Toggle
                label={`${key} access`}
                checked={access[key]}
                onChange={() => setAccess({ ...access, [key]: !access[key] })}
              />
            </div>
          ))}
        </div>
        <div className="footnote">All apps start off. You can change access anytime.</div>
      </section>
      <div className="bottom-actions">
        <ActionButton
          label="Turn off all access"
          tone="secondary"
          onClick={() => setAccess({ ...initialAccess })}
          full
        />
      </div>
    </main>
  );
}

function TopicTrail({
  current,
  showFlights,
  onDates,
  onFlights,
}: {
  current: "dates" | "flights";
  showFlights: boolean;
  onDates: () => void;
  onFlights: () => void;
}) {
  return (
    <div className="topic-scroll" aria-label="Conversation topics">
      <div className="topic-trail">
        <Topic
          label="Mia’s dates"
          state={current === "dates" ? "current" : "past"}
          onClick={onDates}
        />
        {showFlights ? (
          <Topic
            label="Flights"
            state={current === "flights" ? "current" : "past"}
            onClick={onFlights}
          />
        ) : null}
      </div>
    </div>
  );
}

function Topic({
  label,
  state,
  onClick,
}: {
  label: string;
  state: "past" | "current";
  onClick: () => void;
}) {
  return (
    <ActionButton
      label={
        <span className="topic-inner">
          <img
            className="topic-line"
            src={state === "current" ? "/assets/137f7.svg" : "/assets/b7235.svg"}
            alt=""
          />
          <span>{label}</span>
        </span>
      }
      tone="topic"
      onClick={onClick}
      ariaCurrent={state === "current" ? "page" : undefined}
      className={state === "current" ? "topic current" : "topic"}
    />
  );
}

function Message({ role, children }: { role: "user" | "assistant"; children: React.ReactNode }) {
  return <div className={`message ${role}`}>{children}</div>;
}

function ResponseCard({
  title,
  meta,
  children,
  action,
  onAction,
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="response-card">
      <div className="headline">{title}</div>
      {meta ? <div className="footnote">{meta}</div> : null}
      <div className="callout">{children}</div>
      {action && onAction ? (
        <ActionButton label={action} tone="primary" onClick={onAction} />
      ) : null}
    </div>
  );
}

function ChatShell({
  children,
  current,
  showFlights,
  onHome,
  onDates,
  onFlights,
  onSend,
}: {
  children: React.ReactNode;
  current?: "dates" | "flights";
  showFlights?: boolean;
  onHome: () => void;
  onDates: () => void;
  onFlights: () => void;
  onSend: (message: string) => void;
}) {
  return (
    <main className="screen chat-screen">
      <Nav onHome={onHome} />
      {current ? (
        <TopicTrail
          current={current}
          showFlights={Boolean(showFlights)}
          onDates={onDates}
          onFlights={onFlights}
        />
      ) : null}
      <section className="conversation">
        <div className="message-stack">{children}</div>
      </section>
      <div className="composer-wrap">
        <Composer onSend={onSend} />
      </div>
    </main>
  );
}

function ReadyChat({ onHome, onSend }: { onHome: () => void; onSend: (message: string) => void }) {
  return (
    <ChatShell
      onHome={onHome}
      onDates={() => undefined}
      onFlights={() => undefined}
      onSend={onSend}
    >
      <Message role="assistant">What can I help you with today?</Message>
    </ChatShell>
  );
}

function Availability({
  onHome,
  onSearch,
  onSend,
}: {
  onHome: () => void;
  onSearch: () => void;
  onSend: (message: string) => void;
}) {
  return (
    <ChatShell
      current="dates"
      onHome={onHome}
      onDates={() => undefined}
      onFlights={() => undefined}
      onSend={onSend}
    >
      <Message role="user">Is Mia free Nov 14–15?</Message>
      <Message role="assistant">
        Mia shared: “I’m free Nov 14–15. Come visit!”
        <br />
        Sample message · Nov 10. Her private calendar is not accessible.
      </Message>
      <ResponseCard
        title="Find flights for your visit"
        meta="SFO → JFK · Nov 13–16 · 1 adult"
        action="Search flights online"
        onAction={onSearch}
      >
        Search return fares under $500. Only trip details are shared; your messages stay on this
        device.
      </ResponseCard>
    </ChatShell>
  );
}

function FlightChoices({
  selected,
  setSelected,
  onHome,
  onDates,
  onReview,
  onSend,
}: {
  selected: "stops" | "nonstop";
  setSelected: (value: "stops" | "nonstop") => void;
  onHome: () => void;
  onDates: () => void;
  onReview: () => void;
  onSend: (message: string) => void;
}) {
  return (
    <ChatShell
      current="flights"
      showFlights
      onHome={onHome}
      onDates={onDates}
      onFlights={() => undefined}
      onSend={onSend}
    >
      <Message role="user">Find return flights under $500.</Message>
      <Message role="assistant">
        These sample return fares fit Nov 13–16. Choose an option, or ask me to compare them.
      </Message>
      <div className="response-card selection-card">
        <div className="headline">Choose your flight</div>
        <div className="footnote">SFO–JFK · 1 adult · Return · Demo fares</div>
        <FlightOption
          label="1 stop · $329 return"
          selected={selected === "stops"}
          onClick={() => setSelected("stops")}
        />
        <FlightOption
          label="Nonstop · $429 return"
          selected={selected === "nonstop"}
          onClick={() => setSelected("nonstop")}
        />
        <ActionButton label="Review selected flight" tone="primary" onClick={onReview} />
      </div>
    </ChatShell>
  );
}

function FlightOption({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <ActionButton
      label={
        <span className="option-inner">
          <span className="radio">
            <img src="/assets/761e3.svg" alt="" />
            {selected ? <img className="radio-mark" src="/assets/b84a7.svg" alt="" /> : null}
          </span>
          <span>{label}</span>
        </span>
      }
      tone="option"
      onClick={onClick}
      ariaPressed={selected}
      full
    />
  );
}

function Review({
  selected,
  onHome,
  onDates,
  onFlights,
  onConfirm,
  onSend,
}: {
  selected: "stops" | "nonstop";
  onHome: () => void;
  onDates: () => void;
  onFlights: () => void;
  onConfirm: () => void;
  onSend: (message: string) => void;
}) {
  const price = selected === "nonstop" ? "$429" : "$329";
  const route = selected === "nonstop" ? "Nonstop" : "1 stop";

  return (
    <ChatShell
      current="flights"
      showFlights
      onHome={onHome}
      onDates={onDates}
      onFlights={onFlights}
      onSend={onSend}
    >
      <Message role="user">Review the selected flight.</Message>
      <ResponseCard
        title="Review before booking"
        meta="Example Air · Sample fare"
        action={`Confirm booking · ${price}`}
        onAction={onConfirm}
      >
        SFO → JFK · Nov 13, 08:00–16:30
        <br />
        JFK → SFO · Nov 16, 17:00–20:30
        <br />
        {route} · Economy · Local times
        <br />
        Taxes + carry-on; checked bag extra
        <br />
        Sample traveler · Visa •4242
        <br />
        {price} total return · Demo only
      </ResponseCard>
      <Message role="assistant">
        Booking requires your confirmation. Sharing with Mia is a separate action.
      </Message>
    </ChatShell>
  );
}

function Confirmation({
  shared,
  onShare,
  onHome,
  onDates,
  onFlights,
  onSend,
}: {
  shared: boolean;
  onShare: () => void;
  onHome: () => void;
  onDates: () => void;
  onFlights: () => void;
  onSend: (message: string) => void;
}) {
  return (
    <ChatShell
      current="flights"
      showFlights
      onHome={onHome}
      onDates={onDates}
      onFlights={onFlights}
      onSend={onSend}
    >
      <Message role="user">Confirm the booking.</Message>
      <ResponseCard title="Flight booked · Demo" meta="Sample confirmation">
        No booking confirmed.
      </ResponseCard>
      <ResponseCard
        title={shared ? "Itinerary shared · Demo" : "Send your itinerary to Mia?"}
        meta="Messages · Recipient: Mia"
        action={shared ? undefined : "Send to Mia"}
        onAction={shared ? undefined : onShare}
      >
        {shared ? "Your sample itinerary was shared with Mia." : "No itinerary to share yet."}
      </ResponseCard>
    </ChatShell>
  );
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [access, setAccess] = useState(initialAccess);
  const [selected, setSelected] = useState<"stops" | "nonstop">("nonstop");
  const [shared, setShared] = useState(false);

  const home = () => setScreen("home");
  const sendMessage = (message: string) => {
    const normalized = message.toLowerCase();
    if (normalized.includes("mia") || normalized.includes("free") || screen === "ready") {
      setScreen(access.Messages ? "availability" : "permission");
      return;
    }
    if (normalized.includes("flight") || normalized.includes("fare")) {
      setScreen("flights");
    }
  };

  if (screen === "home") {
    return (
      <Home
        onVisit={() => setScreen(access.Messages ? "availability" : "permission")}
        onSettings={() => setScreen("settings")}
        onAsk={() => setScreen("ready")}
      />
    );
  }

  if (screen === "permission") {
    return (
      <Permission
        onHome={home}
        onAllow={() => {
          setAccess({ ...access, Messages: true });
          setScreen("availability");
        }}
        onContinue={() => setScreen("availability")}
      />
    );
  }

  if (screen === "settings") {
    return <Settings access={access} setAccess={setAccess} onHome={home} />;
  }

  if (screen === "ready") {
    return <ReadyChat onHome={home} onSend={sendMessage} />;
  }

  if (screen === "availability") {
    return (
      <Availability onHome={home} onSearch={() => setScreen("flights")} onSend={sendMessage} />
    );
  }

  if (screen === "flights") {
    return (
      <FlightChoices
        selected={selected}
        setSelected={setSelected}
        onHome={home}
        onDates={() => setScreen("availability")}
        onReview={() => setScreen("review")}
        onSend={sendMessage}
      />
    );
  }

  if (screen === "review") {
    return (
      <Review
        selected={selected}
        onHome={home}
        onDates={() => setScreen("availability")}
        onFlights={() => setScreen("flights")}
        onConfirm={() => setScreen("confirmation")}
        onSend={sendMessage}
      />
    );
  }

  return (
    <Confirmation
      shared={shared}
      onShare={() => setShared(true)}
      onHome={home}
      onDates={() => setScreen("availability")}
      onFlights={() => setScreen("flights")}
      onSend={sendMessage}
    />
  );
}
