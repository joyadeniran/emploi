import React from "react";
import { CareerTwinBot } from "@/components/CareerTwinBot";

export function Default() {
  return <CareerTwinBot />;
}

export function Small() {
  return <CareerTwinBot size={120} />;
}

export function Large() {
  return <CareerTwinBot size={280} />;
}
