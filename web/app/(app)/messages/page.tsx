import { MessageSquare } from "lucide-react";
import { PagePlaceholder } from "@/components/PagePlaceholder";

export const metadata = { title: "Messages — Emploi" };

export default function MessagesPage() {
  return (
    <PagePlaceholder
      icon={MessageSquare}
      title="Messages"
      blurb="Conversations with employers and your Career Twin, all in one inbox."
    />
  );
}
