import React from "react";
import { AppShell } from "@/components/AppShell";

const noOp = async () => {};
const user = { name: "Amara Okonkwo", email: "amara@example.com", image: null };

export function WithContent() {
  return (
    <div style={{ height: 600, overflow: "hidden" }}>
      <AppShell user={user} signOutAction={noOp}>
        <div style={{ padding: 24 }}>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: "var(--color-ink)" }}>
            Good morning, Amara
          </h1>
          <p style={{ color: "var(--color-muted)", marginTop: 4, fontSize: 14 }}>
            You have 3 new job matches and 1 interview scheduled.
          </p>
        </div>
      </AppShell>
    </div>
  );
}
