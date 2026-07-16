"use client";

import { useState } from "react";
import { Sun, Moon, Monitor } from "lucide-react";

type Theme = "system" | "light" | "dark";

const VALID: Theme[] = ["system", "light", "dark"];

function readStored(): Theme {
  if (typeof window === "undefined") return "system";
  const v = localStorage.getItem("emploi-theme");
  return v && VALID.includes(v as Theme) ? (v as Theme) : "system";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "dark") {
    root.setAttribute("data-theme", "dark");
  } else if (theme === "light") {
    root.setAttribute("data-theme", "light");
  } else {
    root.removeAttribute("data-theme");
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readStored);

  function pick(next: Theme) {
    setTheme(next);
    localStorage.setItem("emploi-theme", next);
    applyTheme(next);
  }

  const options: { value: Theme; icon: typeof Sun; label: string }[] = [
    { value: "light", icon: Sun, label: "Light" },
    { value: "system", icon: Monitor, label: "System" },
    { value: "dark", icon: Moon, label: "Dark" },
  ];

  return (
    <div className="inline-flex items-center rounded-full border border-line bg-surface p-1">
      {options.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => pick(value)}
          title={label}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold transition-colors ${
            theme === value
              ? "bg-card text-ink shadow-sm"
              : "text-faint hover:text-muted"
          }`}
        >
          <Icon size={14} />
          <span className="hidden sm:inline">{label}</span>
        </button>
      ))}
    </div>
  );
}
