import React from "react";
import { PagePlaceholder } from "@/components/PagePlaceholder";
import { Briefcase, MessageSquare, BarChart3 } from "lucide-react";

export function JobMatches() {
  return (
    <div style={{ padding: 24 }}>
      <PagePlaceholder
        icon={Briefcase}
        title="Job Matches"
        blurb="Personalized roles matched to your Career Twin profile."
      />
    </div>
  );
}

export function Messages() {
  return (
    <div style={{ padding: 24 }}>
      <PagePlaceholder
        icon={MessageSquare}
        title="Messages"
        blurb="Communicate directly with recruiters and hiring managers."
        note="Recruiter messaging is coming soon — your profile is already visible to matched employers."
      />
    </div>
  );
}

export function Insights() {
  return (
    <div style={{ padding: 24 }}>
      <PagePlaceholder
        icon={BarChart3}
        title="Career Insights"
        blurb="Understand your market value and application pipeline performance."
      />
    </div>
  );
}
