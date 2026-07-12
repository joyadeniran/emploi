import { Sparkles } from "lucide-react";
import { PagePlaceholder } from "@/components/PagePlaceholder";

export const metadata = { title: "Career Twin — Emploi" };

export default function CareerTwinPage() {
  return (
    <PagePlaceholder
      icon={Sparkles}
      title="Career Twin"
      blurb="Your smart, living profile — experience, skills, education and goals, built from your CV and every conversation."
      note="Profile editing arrives here next. Upload a new CV or chat with your Twin to keep it sharp meanwhile."
    />
  );
}
