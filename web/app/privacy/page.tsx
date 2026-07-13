import Link from "next/link";

export const metadata = { title: "Privacy Policy — Emploi" };

export default function PrivacyPage() {
  return <Legal title="Privacy Policy"><p>Emploi is a brand of Crost Limited (RC 9526947), the controller for the personal data described here.</p><h2>What we process</h2><p>We process the CVs, Career Twin profile data, job information, application records, and Google account details you choose to provide. Do not provide bank details, BVN, NIN, passport details, or payment-card data.</p><h2>How it is used</h2><p>CV text and profile information may be sent to Google’s Gemini API to extract your Career Twin and generate tailored documents. We do not sell your data, use it for advertising, or share it with employers without your action.</p><h2>Retention and deletion</h2><p>Signed-in data is stored for your account until you delete it. Use Settings → Delete all my data to permanently erase your Career Twin, applications, matches, and events. Contact <a href="mailto:hello@emploihq.com">hello@emploihq.com</a> for access or correction requests.</p><h2>Verification</h2><p>Trust Checks use public domain and website signals. They reduce risk; they are not a guarantee that an employer is legitimate.</p></Legal>;
}

export function Legal({ title, children }: { title: string; children: React.ReactNode }) {
  return <main className="mx-auto min-h-screen max-w-3xl px-5 py-10 sm:py-16"><Link href="/login" className="text-sm font-bold text-brand">← Back to Emploi</Link><article className="mt-6 rounded-3xl border border-line bg-white p-6 shadow-card sm:p-10"><h1 className="text-3xl font-extrabold tracking-tight">{title}</h1><p className="mt-2 text-sm text-muted">Last updated: 13 July 2026</p><div className="legal-copy mt-8 space-y-5 text-sm leading-7 text-muted">{children}</div><p className="mt-8 border-t border-line pt-5 text-xs text-muted"><Link className="font-bold text-brand" href="/terms">Terms of Service</Link> · © 2026 Crost Limited</p></article></main>;
}
