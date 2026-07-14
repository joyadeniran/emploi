"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Send, Sparkles } from "lucide-react";

type Msg = { role: "user" | "assistant"; content: string; updates?: string[] };

const WELCOME: Msg = {
  role: "assistant",
  content:
    "Hi, I'm your Career Twin. Ask me anything — interview advice, how to position your experience, whether a role fits you. If you tell me something new about your goals or skills, I'll remember it in your profile.",
};

const UPDATE_LABELS: Record<string, string> = {
  goals: "Career goals",
  title: "Headline",
  skills: "Skills",
  location: "Location",
  experience: "Experience",
  education: "Education",
  name: "Name",
};

export function CareerTwinChat() {
  const [messages, setMessages] = useState<Msg[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setError("");
    setInput("");
    const outgoing: Msg = { role: "user", content: text };
    // History for the model: everything except the canned welcome.
    const history = [...messages.filter((m) => m !== WELCOME), outgoing]
      .slice(-20)
      .map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, outgoing]);
    setBusy(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.error || "chat failed");
      }
      const data = (await res.json()) as { reply: string; profile_updates: Record<string, string> };
      const updates = Object.keys(data.profile_updates ?? {}).map((k) => UPDATE_LABELS[k] ?? k);
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply, updates }]);
    } catch (e) {
      const message = e instanceof Error ? e.message : "";
      setError(
        message.includes("429") || message.toLowerCase().includes("rate")
          ? "You're sending messages a little fast — give it a minute and try again."
          : "I couldn't answer that just now. Your message wasn't lost — try sending it again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100dvh-8.5rem)] max-w-3xl flex-col">
      <header className="mb-4">
        <p className="flex items-center gap-2 text-sm font-bold text-brand"><Sparkles size={16} /> Career Twin</p>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">Messages</h1>
        <p className="mt-1 text-sm text-muted">
          Career advice from your Twin. New facts you share are saved to your profile.
        </p>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto rounded-2xl border border-line bg-white p-4 shadow-card sm:p-6">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={
              m.role === "user"
                ? "max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-r from-brand-violet to-brand-indigo px-4 py-3 text-sm leading-relaxed text-white"
                : "max-w-[85%] rounded-2xl rounded-bl-md bg-surface px-4 py-3 text-sm leading-relaxed text-ink"
            }>
              <p className="whitespace-pre-wrap">{m.content}</p>
              {m.updates?.length ? (
                <p className="mt-2 flex flex-wrap gap-1.5">
                  {m.updates.map((u) => (
                    <span key={u} className="rounded-full bg-good-soft px-2 py-0.5 text-[11px] font-bold text-good">
                      Profile updated: {u}
                    </span>
                  ))}
                </p>
              ) : null}
            </div>
          </div>
        ))}
        {busy ? (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-surface px-4 py-3">
              <Loader2 size={16} className="animate-spin text-brand" aria-label="Your Career Twin is thinking" />
            </div>
          </div>
        ) : null}
        {error ? <p role="alert" className="text-center text-sm font-semibold text-warn">{error}</p> : null}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); send(); }}
        className="mt-4 flex items-end gap-2"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          rows={1}
          placeholder="Ask your Career Twin anything…"
          className="max-h-32 min-h-[3rem] w-full resize-y rounded-2xl border border-line bg-white px-4 py-3 text-sm leading-relaxed outline-none focus:border-brand"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          aria-label="Send message"
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand text-white transition-transform hover:-translate-y-0.5 disabled:opacity-50"
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
