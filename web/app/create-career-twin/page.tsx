"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/Logo";
import {
  FileText,
  X,
  Plus,
  CheckCircle2,
  Loader2,
  Search,
  ShieldCheck,
  PenLine,
  BarChart3,
  Sparkles,
  MapPin,
  Check,
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface CareerTwin {
  name: string;
  headline: string;
  current_role: string;
  experience_years: string;
  location: string;
  skills: string[];
  bio: string;
  preferred_roles: string[];
  preferred_industries: string[];
  employment_type: string;
  remote_preference: string;
  preferred_locations: string[];
  salary_min: number;
  salary_max: number;
  currency: string;
  career_goals: string[];
  availability: string;
}

const EMPTY_TWIN: CareerTwin = {
  name: "",
  headline: "",
  current_role: "",
  experience_years: "1 year",
  location: "",
  skills: [],
  bio: "",
  preferred_roles: [],
  preferred_industries: [],
  employment_type: "Full-time",
  remote_preference: "Remote or Hybrid",
  preferred_locations: [],
  salary_min: 0,
  salary_max: 0,
  currency: "USD",
  career_goals: [],
  availability: "Open to new opportunities",
};

const GOAL_OPTIONS = [
  "Career Growth",
  "Higher salary",
  "Remote work",
  "Learning new skills",
  "Work-life balance",
  "Stability",
];

// ─── Progress dots (steps 2–9) ────────────────────────────────────────────────

function ProgressDots({ step }: { step: number }) {
  // Stages: 1=Upload, 2=Review, 3=Preferences, 4=Goals, 5=Activate
  // step 2–3 → stage 1, step 4–5 → stage 2, step 6 → stage 3, step 7 → stage 4, step 8–9 → stage 5
  const stageOf = (s: number) => {
    if (s <= 3) return 1;
    if (s <= 5) return 2;
    if (s === 6) return 3;
    if (s === 7) return 4;
    return 5;
  };
  const current = stageOf(step);
  const labels = ["Upload", "Review", "Preferences", "Goals", "Activate"];

  return (
    <div className="flex items-center justify-center gap-3">
      {labels.map((label, i) => {
        const stage = i + 1;
        const done = stage < current;
        const active = stage === current;
        return (
          <div key={label} className="flex flex-col items-center gap-1">
            <div
              className={`h-2.5 w-2.5 rounded-full transition-all ${
                done
                  ? "bg-brand-violet"
                  : active
                    ? "bg-brand-violet ring-2 ring-brand-violet/30 ring-offset-1"
                    : "border-2 border-line bg-white"
              }`}
            />
            <span className={`text-[10px] font-semibold ${active ? "text-brand" : done ? "text-brand/60" : "text-faint"}`}>
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ─── Animated checklist ────────────────────────────────────────────────────

function AnimatedChecklist({
  items,
  delayMs = 500,
  lastSpinner = true,
}: {
  items: string[];
  delayMs?: number;
  lastSpinner?: boolean;
}) {
  const [visible, setVisible] = useState(0);

  useEffect(() => {
    setVisible(0);
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setVisible(i);
      if (i >= items.length) clearInterval(interval);
    }, delayMs);
    return () => clearInterval(interval);
  }, [items, delayMs]);

  return (
    <ul className="space-y-3">
      {items.map((item, idx) => {
        if (idx >= visible) return null;
        const isLast = idx === items.length - 1;
        const spinner = lastSpinner && isLast && visible === items.length;
        return (
          <li key={item} className="flex items-center gap-3 text-sm font-semibold animate-fade-in">
            {spinner ? (
              <Loader2 size={18} className="shrink-0 animate-spin text-brand" />
            ) : (
              <CheckCircle2 size={18} className="shrink-0 text-good" />
            )}
            {item}
          </li>
        );
      })}
    </ul>
  );
}

// ─── Tag chip input ────────────────────────────────────────────────────────

function TagInput({
  tags,
  onChange,
  placeholder = "Type and press Enter",
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");

  function add() {
    const v = input.trim();
    if (v && !tags.includes(v)) onChange([...tags, v]);
    setInput("");
  }

  return (
    <div className="flex flex-wrap gap-2 rounded-xl border border-line bg-white p-3 focus-within:ring-2 focus-within:ring-brand/20">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1 text-xs font-bold text-brand"
        >
          {tag}
          <button
            type="button"
            onClick={() => onChange(tags.filter((t) => t !== tag))}
            className="hover:text-warn"
            aria-label={`Remove ${tag}`}
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); add(); }
        }}
        placeholder={placeholder}
        className="min-w-[140px] flex-1 border-0 bg-transparent text-sm outline-none placeholder:text-faint"
      />
      {input.trim() && (
        <button
          type="button"
          onClick={add}
          className="flex items-center gap-1 rounded-full bg-brand px-2.5 py-0.5 text-xs font-bold text-white"
        >
          <Plus size={11} /> Add
        </button>
      )}
    </div>
  );
}

// ─── Pill multi-select ─────────────────────────────────────────────────────

function PillSelect({
  options,
  selected,
  onChange,
  max,
}: {
  options: string[];
  selected: string[];
  onChange: (v: string[]) => void;
  max?: number;
}) {
  function toggle(opt: string) {
    if (selected.includes(opt)) {
      onChange(selected.filter((s) => s !== opt));
    } else if (!max || selected.length < max) {
      onChange([...selected, opt]);
    }
  }
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => {
        const on = selected.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={`rounded-full border px-4 py-1.5 text-sm font-semibold transition-all ${
              on
                ? "border-brand bg-brand-soft text-brand"
                : "border-line bg-white text-muted hover:border-brand/40 hover:text-brand"
            }`}
          >
            {on && <Check size={12} className="mr-1 inline" />}
            {opt}
          </button>
        );
      })}
    </div>
  );
}

// ─── Field label ───────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="mb-1.5 block text-sm font-bold text-ink">{children}</label>
  );
}

function Input({
  value,
  onChange,
  placeholder,
  icon,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="relative">
      {icon && (
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint">
          {icon}
        </span>
      )}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full rounded-xl border border-line bg-white py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20 ${icon ? "pl-9 pr-4" : "px-4"}`}
      />
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
    >
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}

// ─── Nav buttons ───────────────────────────────────────────────────────────

function NavButtons({
  onBack,
  onNext,
  nextLabel = "Continue",
  loading = false,
}: {
  onBack?: () => void;
  onNext: () => void;
  nextLabel?: string;
  loading?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 pt-2">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="rounded-full border border-line px-6 py-3 text-sm font-bold text-muted transition hover:border-brand/40 hover:text-brand"
        >
          Back
        </button>
      )}
      <button
        type="button"
        onClick={onNext}
        disabled={loading}
        className="flex flex-1 items-center justify-center gap-2 rounded-full bg-gradient-to-r from-brand-violet to-brand-indigo px-6 py-3 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5 disabled:opacity-60"
      >
        {loading && <Loader2 size={15} className="animate-spin" />}
        {nextLabel}
      </button>
    </div>
  );
}

// ─── Main wizard ───────────────────────────────────────────────────────────

export default function CreateCareerTwinPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [twin, setTwin] = useState<CareerTwin>(EMPTY_TWIN);
  const [userName, setUserName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [extractionFailed, setExtractionFailed] = useState(false);
  const [newSkill, setNewSkill] = useState("");
  const [newRole, setNewRole] = useState("");
  const [newIndustry, setNewIndustry] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function set<K extends keyof CareerTwin>(key: K, value: CareerTwin[K]) {
    setTwin((prev) => ({ ...prev, [key]: value }));
  }

  useEffect(() => {
    const meta = document.querySelector('meta[name="x-user-name"]');
    if (meta) setUserName(meta.getAttribute("content") ?? "");
    // Wake up the Render API in the background so it's ready by the time the
    // user reaches the CV upload step (Render free tier sleeps after 15 min idle).
    fetch("/api/ping").catch(() => {});
  }, []);

  // Step 3 auto-advance — only when no file is being uploaded (skip case)
  useEffect(() => {
    if (step !== 3) return;
    if (uploading) return; // wait for upload to finish; handleUploadContinue advances step
    const timer = setTimeout(() => setStep(4), 2200);
    return () => clearTimeout(timer);
  }, [step, uploading]);

  // Step 8 — save & complete, then advance
  const doActivate = useCallback(async () => {
    try {
      await fetch("/api/career-twin", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: twin }),
      });
      await fetch("/api/career-twin/complete", { method: "POST" });
    } catch {
      /* best-effort — advance anyway */
    }
    setTimeout(() => setStep(9), 2500);
  }, [twin]);

  useEffect(() => {
    if (step === 8) doActivate();
  }, [step, doActivate]);

  async function handleUploadContinue() {
    if (!file) { setStep(3); return; } // no file → skip → 2.2s timer advances
    setExtractionFailed(false);
    setUploading(true);
    setStep(3);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/career-twin/upload", { method: "POST", body: formData });
      if (res.ok) {
        const json = await res.json();
        if (json.career_twin) {
          setTwin((prev) => ({ ...prev, ...json.career_twin }));
        } else {
          setExtractionFailed(true);
        }
      } else {
        setExtractionFailed(true);
      }
    } catch {
      setExtractionFailed(true);
    } finally {
      setUploading(false);
      setStep(4); // advance only after upload resolves (success or failure)
    }
  }

  // ── Step 1: Welcome ────────────────────────────────────────────────────────
  if (step === 1) {
    return (
      <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-surface px-4">
        <div aria-hidden className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-brand-violet/20 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-brand-indigo/20 blur-3xl" />

        <div className="rise-in w-full max-w-lg text-center">
          <div className="flex justify-center">
            <LogoMark size={48} />
          </div>
          <h1 className="mt-8 text-3xl font-extrabold tracking-tight sm:text-4xl">
            {userName ? `Welcome, ${userName}.` : "Welcome to Emploi."}
          </h1>
          <p className="mx-auto mt-5 max-w-sm text-base leading-relaxed text-muted">
            I&apos;m Emploi. Today we&apos;ll create your Career Twin. Once it&apos;s ready,
            it&apos;ll continuously search, verify and prepare opportunities that match
            your goals. It usually takes about 2 minutes.
          </p>
          <button
            onClick={() => setStep(2)}
            className="mt-10 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-brand-violet to-brand-indigo px-8 py-4 text-base font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5"
          >
            <Sparkles size={18} />
            Create my Career Twin
          </button>
          <div className="mt-5">
            <button
              onClick={() => router.push("/dashboard")}
              className="text-sm font-semibold text-faint hover:text-muted"
            >
              I&apos;ll do this later
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Shared wrapper for steps 2–9 ──────────────────────────────────────────
  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-surface px-4 py-12">
      <div aria-hidden className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-brand-violet/15 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-brand-indigo/15 blur-3xl" />

      {/* Logo top-left */}
      <div className="absolute left-6 top-6">
        <LogoMark size={28} />
      </div>

      {/* Progress dots */}
      <div className="mb-8 w-full max-w-lg">
        <ProgressDots step={step} />
      </div>

      {/* Card */}
      <div className="rise-in w-full max-w-lg rounded-3xl border border-white/70 bg-white/80 p-8 shadow-card backdrop-blur-xl">

        {/* ── Step 2: Upload resume ───────────────────────────────────────── */}
        {step === 2 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">Upload your resume</h2>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">
                We&apos;ll use AI to extract your information and build your profile.
              </p>
            </div>

            {file ? (
              <div className="flex items-center gap-3 rounded-2xl border border-brand-soft bg-brand-soft/40 px-5 py-4">
                <FileText size={22} className="shrink-0 text-brand" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold">{file.name}</p>
                  <p className="text-xs text-muted">{(file.size / 1024).toFixed(0)} KB</p>
                </div>
                <button
                  onClick={() => setFile(null)}
                  className="text-xs font-bold text-brand hover:underline"
                >
                  Replace
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-line bg-surface/60 px-6 py-10 text-center transition hover:border-brand/40 hover:bg-brand-soft/20"
              >
                <FileText size={32} className="text-faint" />
                <div>
                  <p className="text-sm font-bold">Drag and drop your resume PDF here</p>
                  <p className="mt-1 text-xs text-muted">or click to browse · Max 10 MB</p>
                </div>
              </button>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f && f.size <= 10 * 1024 * 1024) setFile(f);
              }}
            />

            <p className="flex items-center gap-2 text-xs text-muted">
              <ShieldCheck size={14} className="shrink-0 text-brand" />
              Your data is secure and never shared without your permission.
            </p>

            <NavButtons
              onNext={handleUploadContinue}
              loading={uploading}
              nextLabel={file ? "Continue" : "Skip for now"}
            />
          </div>
        )}

        {/* ── Step 3: Extracting ─────────────────────────────────────────── */}
        {step === 3 && (
          <div className="space-y-8 text-center">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">Extracting your information</h2>
              <p className="mt-1.5 text-sm text-muted">This usually takes less than a minute.</p>
            </div>

            <div className="flex justify-center">
              <div className="relative flex h-24 w-24 items-center justify-center">
                <div className="absolute inset-0 animate-ping rounded-full bg-brand-violet/20" />
                <div className="absolute inset-2 animate-pulse rounded-full bg-brand-violet/30" />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-brand-violet to-brand-indigo shadow-pop">
                  <Sparkles size={28} className="text-white" />
                </div>
              </div>
            </div>

            <div className="text-left">
              <AnimatedChecklist
                items={[
                  "Reading your resume",
                  "Identifying experience",
                  "Extracting skills",
                  "Building your profile",
                ]}
                delayMs={450}
              />
            </div>

            <p className="rounded-xl bg-surface px-4 py-3 text-xs font-semibold text-muted">
              💡 The more complete your resume, the better your matches.
            </p>
          </div>
        )}

        {/* ── Step 4: Review part 1 ──────────────────────────────────────── */}
        {step === 4 && (
          <div className="space-y-5">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-2xl font-extrabold tracking-tight">Review &amp; edit your information</h2>
                {!extractionFailed && <span className="rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-bold text-brand">AI Extracted</span>}
              </div>
              {extractionFailed ? (
                <p className="mt-2 rounded-xl border border-amber/30 bg-amber-soft px-4 py-2.5 text-xs font-semibold text-ink">
                  We couldn&apos;t extract text from your CV — it may be image-only or password-protected. Please fill in your details below.
                </p>
              ) : (
                <p className="mt-1.5 text-sm text-muted">We extracted the details below. Please review and make any changes.</p>
              )}
            </div>

            <div className="space-y-4">
              <div>
                <Label>Full name</Label>
                <Input value={twin.name} onChange={(v) => set("name", v)} placeholder="e.g. Joy Adesola" />
              </div>
              <div>
                <Label>Professional headline</Label>
                <Input value={twin.headline} onChange={(v) => set("headline", v)} placeholder="e.g. Product Designer" />
              </div>
              <div>
                <Label>Current role</Label>
                <Input value={twin.current_role} onChange={(v) => set("current_role", v)} placeholder="e.g. Designer at Paystack" />
              </div>
              <div>
                <Label>Work experience</Label>
                <Select
                  value={twin.experience_years}
                  onChange={(v) => set("experience_years", v)}
                  options={["1 year", "2 years", "3 years", "4 years", "5 years", "6–10 years", "10+ years"]}
                />
              </div>
            </div>

            <NavButtons onBack={() => setStep(2)} onNext={() => setStep(5)} />
          </div>
        )}

        {/* ── Step 5: Review part 2 ──────────────────────────────────────── */}
        {step === 5 && (
          <div className="space-y-5">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">A bit more about you</h2>
              <p className="mt-1.5 text-sm text-muted">Review and edit your location, skills and bio.</p>
            </div>

            <div className="space-y-4">
              <div>
                <Label>Location</Label>
                <Input
                  value={twin.location}
                  onChange={(v) => set("location", v)}
                  placeholder="e.g. Lagos, Nigeria"
                  icon={<MapPin size={15} />}
                />
              </div>
              <div>
                <Label>Skills</Label>
                <div className="flex flex-wrap gap-2">
                  {twin.skills.map((skill) => (
                    <span
                      key={skill}
                      className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1 text-xs font-bold text-brand"
                    >
                      {skill}
                      <button
                        type="button"
                        onClick={() => set("skills", twin.skills.filter((s) => s !== skill))}
                        aria-label={`Remove ${skill}`}
                        className="hover:text-warn"
                      >
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                  <div className="flex items-center gap-1">
                    <input
                      value={newSkill}
                      onChange={(e) => setNewSkill(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          const v = newSkill.trim();
                          if (v && !twin.skills.includes(v)) set("skills", [...twin.skills, v]);
                          setNewSkill("");
                        }
                      }}
                      placeholder="+ Add skill"
                      className="rounded-full border border-dashed border-line px-3 py-1 text-xs outline-none focus:border-brand"
                    />
                  </div>
                </div>
              </div>
              <div>
                <Label>Bio / Summary</Label>
                <textarea
                  value={twin.bio}
                  onChange={(e) => set("bio", e.target.value)}
                  placeholder="A short summary of your experience and what you're looking for…"
                  rows={4}
                  className="w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
                />
              </div>
            </div>

            <NavButtons onBack={() => setStep(4)} onNext={() => setStep(6)} />
          </div>
        )}

        {/* ── Step 6: Career preferences ────────────────────────────────── */}
        {step === 6 && (
          <div className="space-y-5">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">Career preferences</h2>
              <p className="mt-1.5 text-sm text-muted">Tell us what kind of opportunities you&apos;re looking for.</p>
            </div>

            <div className="space-y-4">
              <div>
                <Label>Job type</Label>
                <Select
                  value={twin.employment_type}
                  onChange={(v) => set("employment_type", v)}
                  options={["Full-time", "Part-time", "Contract", "Freelance"]}
                />
              </div>
              <div>
                <Label>Work arrangement</Label>
                <Select
                  value={twin.remote_preference}
                  onChange={(v) => set("remote_preference", v)}
                  options={["Remote", "Hybrid", "On-site", "Remote or Hybrid"]}
                />
              </div>
              <div>
                <Label>Preferred locations</Label>
                <TagInput
                  tags={twin.preferred_locations}
                  onChange={(v) => set("preferred_locations", v)}
                  placeholder="Type a location and press Enter"
                />
              </div>
              <div>
                <Label>Salary range</Label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={twin.salary_min || ""}
                    onChange={(e) => set("salary_min", Number(e.target.value))}
                    placeholder="Min"
                    className="w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
                  />
                  <span className="text-muted">–</span>
                  <input
                    type="number"
                    value={twin.salary_max || ""}
                    onChange={(e) => set("salary_max", Number(e.target.value))}
                    placeholder="Max"
                    className="w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
                  />
                  <Select
                    value={twin.currency}
                    onChange={(v) => set("currency", v)}
                    options={["USD", "NGN", "GBP"]}
                  />
                </div>
              </div>
            </div>

            <NavButtons onBack={() => setStep(5)} onNext={() => setStep(7)} />
          </div>
        )}

        {/* ── Step 7: Goals & interests ──────────────────────────────────── */}
        {step === 7 && (
          <div className="space-y-5">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">Goals &amp; Interests</h2>
              <p className="mt-1.5 text-sm text-muted">Help your Career Twin understand what matters most to you.</p>
            </div>

            <div className="space-y-4">
              <div>
                <Label>Target roles <span className="text-faint font-normal">(up to 3)</span></Label>
                <TagInput
                  tags={twin.preferred_roles}
                  onChange={(v) => set("preferred_roles", v.slice(0, 3))}
                  placeholder="e.g. Product Designer"
                />
              </div>
              <div>
                <Label>Industries that interest you</Label>
                <div className="space-y-2">
                  <PillSelect
                    options={["Fintech", "SaaS", "B2B", "E-commerce", "Healthtech", "Edtech"]}
                    selected={twin.preferred_industries}
                    onChange={(v) => set("preferred_industries", v)}
                  />
                  <div className="flex items-center gap-1">
                    <input
                      value={newIndustry}
                      onChange={(e) => setNewIndustry(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          const v = newIndustry.trim();
                          if (v && !twin.preferred_industries.includes(v))
                            set("preferred_industries", [...twin.preferred_industries, v]);
                          setNewIndustry("");
                        }
                      }}
                      placeholder="+ Add industry"
                      className="rounded-full border border-dashed border-line px-3 py-1 text-xs outline-none focus:border-brand"
                    />
                  </div>
                </div>
              </div>
              <div>
                <Label>What&apos;s most important to you right now?</Label>
                <div className="space-y-2">
                  {GOAL_OPTIONS.map((g) => (
                    <label key={g} className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 transition hover:border-brand/40">
                      <input
                        type="radio"
                        name="goal"
                        value={g}
                        checked={twin.career_goals[0] === g}
                        onChange={() => set("career_goals", [g])}
                        className="accent-brand"
                      />
                      <span className="text-sm font-semibold">{g}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <NavButtons onBack={() => setStep(6)} onNext={() => setStep(8)} />
          </div>
        )}

        {/* ── Step 8: Activating ─────────────────────────────────────────── */}
        {step === 8 && (
          <div className="space-y-8 text-center">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">Creating your Career Twin</h2>
              <p className="mt-1.5 text-sm text-muted">Almost there! We&apos;re personalising your experience and getting to work.</p>
            </div>

            <div className="flex justify-center">
              <div className="relative flex h-24 w-24 items-center justify-center">
                <div className="absolute inset-0 animate-ping rounded-full bg-brand-violet/20" />
                <div className="absolute inset-2 animate-pulse rounded-full bg-brand-violet/30" />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-brand-violet to-brand-indigo shadow-pop">
                  <Sparkles size={28} className="text-white" />
                </div>
              </div>
            </div>

            <div className="text-left">
              <AnimatedChecklist
                items={[
                  "Saving your profile",
                  "Understanding your goals",
                  "Setting your preferences",
                  "Starting your Career Twin",
                ]}
                delayMs={600}
              />
            </div>
          </div>
        )}

        {/* ── Step 9: All set ────────────────────────────────────────────── */}
        {step === 9 && (
          <div className="space-y-6 text-center">
            <div className="flex justify-center">
              <div className="flex h-20 w-20 animate-scale-in items-center justify-center rounded-full bg-good-soft">
                <CheckCircle2 size={44} className="text-good" />
              </div>
            </div>

            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">Your Career Twin is ready!</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                It will now continuously find, verify and prepare opportunities for you.
              </p>
            </div>

            <ul className="space-y-3 text-left">
              {[
                { icon: Search, label: "Find relevant opportunities", sub: "Matched to your skills and goals" },
                { icon: ShieldCheck, label: "Verify employers", sub: "We protect you from scams" },
                { icon: PenLine, label: "Prepare applications", sub: "Tailored cover letters and CVs" },
                { icon: BarChart3, label: "Track your progress", sub: "All your applications in one place" },
              ].map(({ icon: Icon, label, sub }) => (
                <li key={label} className="flex items-start gap-3 rounded-xl border border-line bg-surface/60 px-4 py-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-soft">
                    <Icon size={16} className="text-brand" />
                  </div>
                  <div>
                    <p className="text-sm font-bold">{label}</p>
                    <p className="text-xs text-muted">{sub}</p>
                  </div>
                </li>
              ))}
            </ul>

            <button
              onClick={() => router.push("/dashboard")}
              className="w-full rounded-full bg-gradient-to-r from-brand-violet to-brand-indigo px-6 py-3.5 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5"
            >
              Go to my dashboard
            </button>

            <a
              href="https://emploihq.com"
              className="block text-sm font-semibold text-muted hover:text-brand"
            >
              Explore how it works
            </a>

            <p className="text-xs text-faint">
              ✨ Your Career Twin is now working. You can close your laptop. We&apos;ll keep looking.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
