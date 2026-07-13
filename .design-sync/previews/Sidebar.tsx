import React from "react";
import { Sidebar } from "@/components/Sidebar";

export function Open() {
  return (
    <div style={{ height: 600, position: "relative", overflow: "hidden" }}>
      <Sidebar open={true} onClose={() => {}} />
    </div>
  );
}

export function Closed() {
  return (
    <div style={{ height: 600, position: "relative", overflow: "hidden" }}>
      <Sidebar open={false} onClose={() => {}} />
    </div>
  );
}
