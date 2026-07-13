import React from "react";
import { LoadingMark } from "@/components/LoadingMark";

export function Default() {
  return <LoadingMark />;
}

export function Small() {
  return <LoadingMark size={48} />;
}

export function Large() {
  return <LoadingMark size={140} />;
}

export function OnSurface() {
  return (
    <div
      style={{
        background: "var(--color-surface)",
        borderRadius: 24,
        padding: 40,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <LoadingMark size={72} label="Loading your matches" />
    </div>
  );
}
