import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

export interface Diagnostics {
  ready_for_launch: boolean;
  open_items: string[];
  config: {
    emploi_api_key?: boolean;
    gemini?: { api_key?: boolean; model?: string };
    groq?: { api_key?: boolean };
    brevo?: { api_key?: boolean; sender_email?: boolean };
    paystack?: { secret_key?: boolean };
    r2_backup?: { endpoint?: boolean; access_key?: boolean; secret_key?: boolean; bucket?: boolean };
    web_app_url?: string;
  };
  last_worker_runs: Record<string, { at?: string; summary?: { ok?: boolean } } | null>;
}

function Dot({ ok }: { ok: boolean }) {
  return ok
    ? <CheckCircle2 size={14} className="text-good" />
    : <XCircle size={14} className="text-warn" />;
}

export function DiagnosticsPanel({ diag }: { diag: Diagnostics }) {
  const c = diag.config ?? {};
  const r2 = c.r2_backup ?? {};
  const r2ok = Boolean(r2.endpoint && r2.access_key && r2.secret_key && r2.bucket);
  const checks: [string, boolean, string?][] = [
    ["Gemini (AI)", Boolean(c.gemini?.api_key), c.gemini?.model],
    ["Groq (AI fallback)", Boolean(c.groq?.api_key)],
    ["Brevo (email)", Boolean(c.brevo?.api_key && c.brevo?.sender_email)],
    ["R2 backup", r2ok, r2ok ? undefined : "no backups → data-loss risk"],
    ["Paystack (billing)", Boolean(c.paystack?.secret_key)],
  ];

  return (
    <div className="space-y-4">
      {diag.ready_for_launch ? (
        <div className="flex items-center gap-2 rounded-2xl border border-good/30 bg-good-soft/40 px-4 py-3 text-sm font-bold text-good">
          <CheckCircle2 size={16} /> All launch-critical config present.
        </div>
      ) : (
        <div className="rounded-2xl border border-amber/30 bg-amber-soft/40 px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-bold text-amber">
            <AlertTriangle size={16} /> {diag.open_items.length} open item{diag.open_items.length === 1 ? "" : "s"} before launch
          </p>
          <ul className="mt-1.5 space-y-0.5">
            {diag.open_items.map((it) => (
              <li key={it} className="text-xs text-ink">• {it}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {checks.map(([label, ok, note]) => (
          <div key={label} className="rounded-xl border border-line bg-card p-3">
            <div className="flex items-center gap-1.5">
              <Dot ok={ok} />
              <span className="text-xs font-bold">{label}</span>
            </div>
            {note ? <p className="mt-1 text-[10px] text-muted">{note}</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
