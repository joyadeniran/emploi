import { Mic } from "lucide-react";
import { PagePlaceholder } from "@/components/PagePlaceholder";

export const metadata = { title: "Interview Prep — Emploi" };

export default function InterviewPrepPage() {
  return (
    <PagePlaceholder
      icon={Mic}
      title="Interview Prep"
      blurb="STAR answers, tough questions and roleplay — built only from your real experience."
    />
  );
}
