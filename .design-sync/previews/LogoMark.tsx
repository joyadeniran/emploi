import React from "react";
import { LogoMark } from "@/components/Logo";

export function Default() {
  return <LogoMark />;
}

export function Large() {
  return <LogoMark size={56} />;
}

export function Small() {
  return <LogoMark size={16} />;
}
