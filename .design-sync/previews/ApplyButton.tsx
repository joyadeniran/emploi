import React from "react";
import { ApplyButton } from "@/components/ApplyButton";

const demoMatch = {
  id: "1",
  title: "Senior Frontend Engineer",
  company: "TechCorp Africa",
  companyInitial: "T",
  companyColor: "#5b4ffd",
  location: "Lagos, Nigeria",
  workMode: "Remote" as const,
  employment: "Full-time",
  salary: "$80k–$100k",
  fit: 88,
  level: "strong" as const,
  reason: "Strong match on React, TypeScript, and product design.",
  verified: true,
  isNew: true,
};

export function Default() {
  return <ApplyButton match={demoMatch} />;
}

export function LowFit() {
  return <ApplyButton match={{ ...demoMatch, fit: 52, verified: false }} />;
}
