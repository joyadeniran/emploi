import React from "react";
import { ProgressRing } from "@/components/ProgressRing";

export function High() {
  return <ProgressRing value={87} label="87%" sublabel="Fit score" />;
}

export function Medium() {
  return <ProgressRing value={65} label="65%" sublabel="Fit score" color="var(--color-amber)" />;
}

export function Low() {
  return <ProgressRing value={38} label="38%" sublabel="Fit score" color="var(--color-warn)" />;
}

export function Compact() {
  return <ProgressRing value={72} size={80} stroke={7} />;
}

export function CustomLabel() {
  return <ProgressRing value={94} label="A+" sublabel="Overall match" size={140} />;
}
