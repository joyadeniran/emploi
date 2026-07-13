import React from "react";
import { Logo } from "@/components/Logo";

export function Default() {
  return <Logo />;
}

export function Large() {
  return <Logo markSize={40} />;
}

export function Small() {
  return <Logo markSize={18} />;
}
