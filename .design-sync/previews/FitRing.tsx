import React from "react";
import { FitRing } from "@/components/ProgressRing";

export function Strong() {
  return <FitRing fit={91} />;
}

export function Good() {
  return <FitRing fit={72} />;
}

export function Weak() {
  return <FitRing fit={43} />;
}

export function Sizes() {
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
      <FitRing fit={88} size={32} />
      <FitRing fit={88} size={48} />
      <FitRing fit={88} size={64} />
    </div>
  );
}
