"use client";

export type GeneratedDraft = { result: string; fit_score: number | null };
export type GeneratedCv = { cv: string; company?: string };

export class GenerationError extends Error {}

/**
 * The three parts of a generated application. `evaluation` is SCREEN-ONLY:
 * it holds the candidate's own gap analysis and "(stretch — verify)" markers,
 * so it must never be exported into a file they might send to an employer.
 */
export type DraftSections = {
  coverLetter: string;
  cvBullets: string;
  evaluation: string;
};

// Must stay in lockstep with core._EVAL_HEADER / _SECTION_PATTERNS. The
// evaluation header has TWO spellings in real model output — "Fit Evaluation"
// AND "Fit Score" — and missing one routes the evaluation into the CV bullets
// (mislabels the gap analysis and empties the "for your eyes only" panel).
const SECTION_RES: [keyof DraftSections, RegExp][] = [
  ["coverLetter", /^\s{0,3}#{1,6}\s*\**\s*cover\s+letter\b/i],
  ["cvBullets", /^\s{0,3}#{1,6}\s*\**\s*cv\s+bullet/i],
  ["evaluation", /^\s{0,3}#{1,6}\s*\**\s*fit\s+(?:evaluation|score)\b/i],
];

/**
 * Mirrors core.split_application. Defensive: unknown headers never throw, and
 * any text before the first recognised header (a preamble, or a whole
 * headerless draft) becomes the cover letter rather than being dropped.
 */
export function splitDraft(text: string): DraftSections {
  const buckets: DraftSections = { coverLetter: "", cvBullets: "", evaluation: "" };
  const lines: Record<keyof DraftSections, string[]> = { coverLetter: [], cvBullets: [], evaluation: [] };
  let current: keyof DraftSections = "coverLetter";

  for (const line of (text ?? "").split("\n")) {
    const hit = SECTION_RES.find(([, re]) => re.test(line));
    if (hit) {
      current = hit[0];
      continue; // drop the header line itself
    }
    lines[current].push(line);
  }
  for (const key of Object.keys(lines) as (keyof DraftSections)[]) {
    buckets[key] = lines[key].join("\n").trim();
  }
  return buckets;
}

/**
 * Polls an async generation job to completion. Both /applications/generate and
 * /applications/cv submit through the same job store and poll endpoint.
 */
async function pollJob<T>(jobId: string, onTick?: (elapsedSeconds: number) => void): Promise<T> {
  const startedAt = Date.now();
  const MAX_WAIT_MS = 100_000;
  const POLL_MS = 2_000;

  while (Date.now() - startedAt < MAX_WAIT_MS) {
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    onTick?.(Math.round((Date.now() - startedAt) / 1000));

    const pollRes = await fetch(`/api/applications/generate/${jobId}`);
    const pollData = await pollRes.json().catch(() => ({}));
    if (!pollRes.ok) {
      throw new GenerationError(pollData?.error || "Lost track of that draft — try again.");
    }
    if (pollData.status === "done") return pollData.generated as T;
    if (pollData.status === "error") throw new GenerationError(pollData.error || "Generation failed.");
    // status === "pending" — keep polling
  }
  throw new GenerationError(
    "This is taking longer than usual. The draft may still finish — try again in a moment, or skip it and apply directly.",
  );
}

async function submit(path: string, body: unknown): Promise<string> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.job_id) {
    throw new GenerationError(data?.error || "Couldn't start generation.");
  }
  return data.job_id as string;
}

/**
 * Submits a tailored-application generation job and polls until it resolves.
 * Generation is two sequential Gemini calls server-side — slow enough to blow
 * past any single request's timeout — so the API returns a job id immediately.
 *
 * `onTick` fires on each poll with elapsed seconds, for progressive status copy.
 */
export async function generateApplication(
  job: { company_name?: string; title?: string; description: string },
  includeReview: boolean,
  onTick?: (elapsedSeconds: number) => void,
): Promise<GeneratedDraft> {
  const jobId = await submit("/api/applications/generate", { job, include_review: includeReview });
  return pollJob<GeneratedDraft>(jobId, onTick);
}

/**
 * Generates a COMPLETE tailored CV (not the draft's bullet fragments) — the
 * artifact a candidate actually sends. One extra Gemini call, which counts
 * against the monthly allowance, so the UI must disclose it before calling.
 */
export async function generateCv(
  job: { company_name?: string; title?: string; description: string },
  onTick?: (elapsedSeconds: number) => void,
): Promise<GeneratedCv> {
  const jobId = await submit("/api/applications/cv", { job });
  return pollJob<GeneratedCv>(jobId, onTick);
}

/**
 * Renders one section into a real .pdf/.docx and triggers the browser download.
 * Never pass the fit evaluation here.
 */
export async function downloadDocument(
  text: string,
  format: "pdf" | "docx",
  title: string,
): Promise<void> {
  const res = await fetch("/api/applications/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, format, title }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new GenerationError(data?.error || "We couldn't build that document — you can still copy the text.");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  // Prefer the server's filename; fall back to a safe local slug.
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  a.download = match?.[1] || `emploi-application.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
