# Emploi Design System — Conventions

**Brand**: Purple-first. Primary color `#5b4ffd` (`--color-brand`). Gradient axis: violet `#8b48fd` → indigo `#435afe`. Use the gradient on CTAs and upgrade prompts.

**Tokens over hardcoded values.** Every color, shadow, and spacing reference should use CSS variables (`--color-brand`, `--color-ink`, `--color-muted`, `--shadow-card`, etc.) — never hex literals in JSX.

**Typography**: "Plus Jakarta Sans" (loaded at runtime via Google Fonts). Not shipped in the bundle — the host page provides it. Headings are `font-extrabold tracking-tight`; body is `text-sm text-muted`; labels are `text-xs font-semibold`.

**Radius language**: buttons and interactive elements are `rounded-xl` (12px); cards and panels are `rounded-2xl` or `rounded-3xl`; avatars/rings are `rounded-full`.

**AppShell** wraps every authenticated page: `Sidebar` (fixed left on desktop, drawer on mobile) + `Topbar` (sticky, blurred) + `<main>`. Do not compose these independently when building full-page screens.

**Fit scoring** uses color semantics: ≥85 = `--color-good` (green), 60–84 = `--color-amber`, <60 = `--color-warn` (red). `FitRing` handles this automatically from the `fit` prop.

**ProgressRing** is the large data-display ring (dashboard metrics, profile completion). `FitRing` is the compact inline variant (job cards, match lists). Don't swap them.

**PagePlaceholder** is the coming-soon state for unbuilt pages — always pass a `LucideIcon`, a `title`, and a `blurb`. The `note` prop overrides the default "on the way" copy.

**Motion**: entry animation is `rise-in` (upward fade-in, 0.5s). Apply on page-level content blocks, not on interactive micro-elements.

**Trust/verification badge**: scam-protection is a core brand promise. Verified employers get a shield badge; unverified get a warning. Never suppress the trust warning copy on low-trust employers.
