import { Bookmark } from "lucide-react";
import { PagePlaceholder } from "@/components/PagePlaceholder";

export const metadata = { title: "Saved Jobs — Emploi" };

export default function SavedPage() {
  return (
    <PagePlaceholder
      icon={Bookmark}
      title="Saved Jobs"
      blurb="Roles you bookmarked to come back to — your Twin keeps their trust checks fresh."
    />
  );
}
