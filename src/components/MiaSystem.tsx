import { createElement, useState, type ReactNode } from "react";

export type ButtonTone = "primary" | "secondary" | "quiet" | "muted" | "soft" | "topic" | "option";

export function ActionButton({
  label,
  tone,
  onClick,
  full,
  className = "",
  ariaPressed,
  ariaCurrent,
}: {
  label: ReactNode;
  tone: ButtonTone;
  onClick: () => void;
  full?: boolean;
  className?: string;
  ariaPressed?: boolean;
  ariaCurrent?: "page";
}) {
  return createElement(
    "button",
    {
      type: "button",
      className: `mia-button ${tone} ${full ? "full" : ""} ${className}`.trim(),
      onClick,
      "aria-pressed": ariaPressed,
      "aria-current": ariaCurrent,
    },
    label,
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return createElement(
    "button",
    {
      type: "button",
      role: "switch",
      "aria-checked": checked,
      "aria-label": label,
      className: `switch ${checked ? "checked" : ""}`,
      onClick: onChange,
    },
    createElement("span", { className: "switch-knob" }),
  );
}

export function Composer({ onSend }: { onSend: (value: string) => void }) {
  const [value, setValue] = useState("");

  const submit = () => {
    const next = value.trim();
    if (!next) return;
    onSend(next);
    setValue("");
  };

  return (
    <div className="composer">
      {createElement("input", {
        value,
        onChange: (event: React.ChangeEvent<HTMLInputElement>) => setValue(event.target.value),
        onKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => {
          if (event.key === "Enter") submit();
        },
        placeholder: "Message",
        "aria-label": "Message",
      })}
      {createElement(
        "button",
        {
          type: "button",
          className: "send-button",
          onClick: submit,
          disabled: !value.trim(),
          "aria-label": "Send message",
        },
        <img src="/assets/b7dc6.svg" alt="" />,
      )}
    </div>
  );
}
