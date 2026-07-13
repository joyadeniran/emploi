# Emploi Design Sync — Notes

## Repo setup

- **Shape**: `package` (no Storybook). Components live in `web/components/`.
- **No dist build**: This is a Next.js App Router project, not a publishable package. The converter synthesizes a bundle entry from all 8 source files in `web/components/`.
- **`pkg` workaround**: Set to `".."` so `PKG_DIR = web/node_modules/.. = web/`. The package name `"web"` is generic (in `GENERIC_PKG`) so the namespace falls back to the dirname `"web"`, then config `globalName = "Emploi"` wins.
- **Tailwind v4**: `app/globals.css` uses `@import "tailwindcss"` (v4 directive syntax). This can't be shipped raw — the bundle uses a pre-processed version at `design-sync-stubs/globals.ds.css`. Regenerate it with: `cd web && npx @tailwindcss/cli -i app/globals.css -o design-sync-stubs/globals.ds.css --minify` whenever tokens change.
- **Next.js stubs**: `Sidebar` uses `next/link` + `next/navigation`, `ApplyButton` uses `next/navigation`. Stubs live in `web/design-sync-stubs/`. The design-sync tsconfig (`web/tsconfig.design-sync.json`) overrides paths to redirect these imports to the stubs. **Do not delete or modify the stubs or the design-sync tsconfig without updating config.**
- **No playwright**: Render check was skipped (`--no-render-check`). Previews are NOT machine-verified. Use `npm i -D playwright && npx playwright install chromium` to enable on a future sync.

## Conventions
- Brand conventions are in `.design-sync/conventions.md` (wired as `readmeHeader`).
- Font is "Plus Jakarta Sans" served at runtime; declared in `runtimeFontPrefixes`.

## Build command (re-sync)
```bash
# Regenerate processed Tailwind CSS if globals.css changed:
(cd web && npx @tailwindcss/cli -i app/globals.css -o design-sync-stubs/globals.ds.css --minify)

# Rebuild:
node .ds-sync/package-build.mjs --config .design-sync/config.json --node-modules web/node_modules --out ./ds-bundle

# Validate:
node .ds-sync/package-validate.mjs ./ds-bundle --no-render-check
```

## Component notes
- **LoadingMark** (added 2026-07-13): its animation keyframes (`loading-mark-pulse`, `.loading-mark-bar`) live in `app/globals.css` — the design-sync CSS must be regenerated (see build command) whenever they change, or DS previews render the mark static.

## Known render warns
- `[RENDER_SKIPPED]`: playwright not installed. Accepted by user on first sync.

## Re-sync risks
- **globals.ds.css** is a pre-processed snapshot of globals.css. If design tokens change (new `--color-*`, font, shadow) and globals.ds.css isn't regenerated, the bundle ships stale tokens.
- **next stubs** are minimal and don't simulate router navigation. ApplyButton's `router.push("/applications")` after apply is a no-op in previews — the button appears idle/done but doesn't route.
- **Topbar** preview includes an image URL from `api.dicebear.com` — that network call may fail in offline or restricted environments, making the avatar fall back to initials (correct behavior).
- **No TypeScript types**: `@types/react` is not in `.ds-sync/node_modules`. DTS extraction was skipped. Prop contracts in `.d.ts` files are weaker.
- **AppShell** preview uses hardcoded content — not connected to real session data. Preview is layout-only.
