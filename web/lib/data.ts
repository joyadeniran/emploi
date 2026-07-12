/**
 * Dashboard data layer.
 *
 * Currently serves demo data so the SaaS shell is fully navigable. When the
 * FastAPI backend (wrapping core.py / verify.py) lands, each accessor below
 * becomes a fetch to it — the components only depend on these types.
 */

export type MatchLevel = "great" | "good" | "fair";

export interface JobMatch {
  id: string;
  title: string;
  company: string;
  companyInitial: string;
  companyColor: string;
  location: string;
  workMode: "Remote" | "Hybrid" | "On-site";
  employment: string;
  salary: string;
  fit: number;
  level: MatchLevel;
  reason: string;
  verified: boolean;
  isNew: boolean;
}

export type ApplicationStatus =
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn";

export interface Application {
  id: string;
  role: string;
  company: string;
  companyInitial: string;
  companyColor: string;
  appliedOn: string;
  status: ApplicationStatus;
  nextStep?: string;
  nextStepDate?: string;
}

export interface TrustCheck {
  company: string;
  score: number;
  verdict: "High Trust" | "Caution" | "Avoid";
  reasons: string[];
}

export interface ProfileChecklistItem {
  label: string;
  done: boolean;
}

export const profile = {
  strength: 92,
  checklist: [
    { label: "Experience added", done: true },
    { label: "Skills added", done: true },
    { label: "Education added", done: true },
    { label: "CV uploaded", done: true },
    { label: "Career goals", done: false },
  ] satisfies ProfileChecklistItem[],
};

export const matches: JobMatch[] = [
  {
    id: "m1",
    title: "Senior Product Manager",
    company: "OPay",
    companyInitial: "O",
    companyColor: "#04114d",
    location: "Lagos, Nigeria",
    workMode: "Remote",
    employment: "Full-time",
    salary: "₦1.2M – ₦2M / year",
    fit: 96,
    level: "great",
    reason:
      "Your fintech product experience and growth metrics map directly to this role's mandate.",
    verified: true,
    isNew: true,
  },
  {
    id: "m2",
    title: "Product Lead",
    company: "Cowrywise",
    companyInitial: "C",
    companyColor: "#f97316",
    location: "Lagos, Nigeria",
    workMode: "Hybrid",
    employment: "Full-time",
    salary: "₦1M – ₦1.6M / year",
    fit: 88,
    level: "great",
    reason:
      "Strong overlap on savings-product strategy; leadership scope is a step up from your last role.",
    verified: true,
    isNew: true,
  },
  {
    id: "m3",
    title: "Product Manager",
    company: "Kuda",
    companyInitial: "K",
    companyColor: "#5b4ffd",
    location: "Lagos, Nigeria",
    workMode: "Remote",
    employment: "Full-time",
    salary: "₦900K – ₦1.4M / year",
    fit: 72,
    level: "good",
    reason:
      "Good core-skills match; the role wants more consumer-credit exposure than your CV shows.",
    verified: true,
    isNew: true,
  },
];

export const applications: Application[] = [
  {
    id: "a1",
    role: "Product Manager",
    company: "Flutterwave",
    companyInitial: "F",
    companyColor: "#f5a623",
    appliedOn: "2 Jul, 2025",
    status: "interview",
    nextStep: "Technical Interview",
    nextStepDate: "10 Jul, 2025",
  },
  {
    id: "a2",
    role: "Senior PM, Payments",
    company: "Paystack",
    companyInitial: "P",
    companyColor: "#04114d",
    appliedOn: "28 Jun, 2025",
    status: "offer",
    nextStep: "Review offer letter",
    nextStepDate: "8 Jul, 2025",
  },
  {
    id: "a3",
    role: "Product Lead",
    company: "PiggyVest",
    companyInitial: "P",
    companyColor: "#0e9f6e",
    appliedOn: "24 Jun, 2025",
    status: "applied",
  },
  {
    id: "a4",
    role: "Growth PM",
    company: "Moniepoint",
    companyInitial: "M",
    companyColor: "#1570ef",
    appliedOn: "18 Jun, 2025",
    status: "rejected",
  },
];

export const trustCheck: TrustCheck = {
  company: "Paystack",
  score: 92,
  verdict: "High Trust",
  reasons: [
    "Website verified",
    "Business email found",
    "Positive review signals",
    "No scam indicators",
  ],
};

export const overview = {
  applied: 12,
  interviews: 5,
  offers: 2,
  interviewRate: "16%",
};

export const plan = {
  name: "Free",
  used: 2,
  limit: 10,
};

export const twinSummary = {
  newMatches: matches.filter((m) => m.isNew).length,
  highMatches: matches.filter((m) => m.fit >= 85).length,
  mediumMatches: matches.filter((m) => m.fit >= 60 && m.fit < 85).length,
  allVerified: matches.every((m) => m.verified),
};

export function firstName(name?: string | null): string {
  return name?.trim().split(/\s+/)[0] ?? "there";
}

export function greeting(date = new Date()): string {
  const h = date.getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export const statusMeta: Record<
  ApplicationStatus,
  { label: string; className: string }
> = {
  applied: { label: "Applied", className: "bg-brand-soft text-brand" },
  interview: { label: "Interview Scheduled", className: "bg-info-soft text-info" },
  offer: { label: "Offer", className: "bg-good-soft text-good" },
  rejected: { label: "Rejected", className: "bg-warn-soft text-warn" },
  withdrawn: { label: "Withdrawn", className: "bg-line text-muted" },
};
