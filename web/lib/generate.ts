"use client";

export type GeneratedDraft = { result: string; fit_score: number | null };

export class GenerationError extends Error {}

/**
 * Submits a tailored-application generation job and polls until it
 * resolves. Generation is two sequential Gemini calls server-side — slow
 * enough to blow past any single request's timeout — so the API returns a
 * job id immediately and this polls GET /api/applications/generate/[id]
 * rather than holding one long-lived request open.
 *
 * `onTick` fires on each poll with elapsed seconds, for progressive status
 * copy ("Writing your draft…" → "Almost there…").
 */
export async function generateApplication(
  job: { company_name?: string; title?: string; description: string },
  includeReview: boolean,
  onTick?: (elapsedSeconds: number) => void,
): Promise<GeneratedDraft> {
  const submitRes = await fetch("/api/applications/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job, include_review: includeReview }),
  });
  const submitData = await submitRes.json().catch(() => ({}));
  if (!submitRes.ok || !submitData.job_id) {
    throw new GenerationError(submitData?.error || "Couldn't start generation.");
  }
  const jobId = submitData.job_id as string;

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
    if (pollData.status === "done") return pollData.generated as GeneratedDraft;
    if (pollData.status === "error") throw new GenerationError(pollData.error || "Generation failed.");
    // status === "pending" — keep polling
  }
  throw new GenerationError(
    "This is taking longer than usual. The draft may still finish — try again in a moment, or skip it and apply directly.",
  );
}
