"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Loader2, RefreshCw } from "lucide-react";

export function UpdateCvButton() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<"idle" | "busy" | "error" | "done">("idle");
  const [fileName, setFileName] = useState("");

  async function handleFile(file: File) {
    setFileName(file.name);
    setState("busy");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/career-twin/upload", { method: "POST", body: formData });
      if (!res.ok) throw new Error();
      setState("done");
      router.refresh();
    } catch {
      setState("error");
    }
  }

  return (
    <div className="rounded-2xl border border-line bg-card p-6 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-extrabold">Update from a new CV</h2>
          <p className="mt-1 text-sm text-muted">
            Upload a newer resume and we&apos;ll refresh your Career Twin&apos;s
            skills, experience, and education — your saved preferences stay
            untouched.
          </p>
        </div>
        <FileText className="mt-0.5 shrink-0 text-brand" size={20} />
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={state === "busy"}
        className="mt-4 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white disabled:opacity-70"
      >
        {state === "busy" ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
        {state === "busy" ? "Reading your CV…" : "Upload new CV"}
      </button>
      {state === "done" ? (
        <p role="status" className="mt-3 text-sm font-semibold text-good">
          {fileName} processed — your Career Twin is updated below.
        </p>
      ) : null}
      {state === "error" ? (
        <p role="alert" className="mt-3 text-sm font-semibold text-warn">
          We couldn&apos;t read that PDF. Make sure it&apos;s a text-based resume
          under 15&nbsp;MB and try again.
        </p>
      ) : null}
    </div>
  );
}
