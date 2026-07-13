import React from "react";
import { Topbar } from "@/components/Topbar";

const noOp = async () => {};

export function WithUser() {
  return (
    <Topbar
      user={{ name: "Amara Okonkwo", email: "amara@example.com", image: null }}
      onMenu={() => {}}
      signOutAction={noOp}
    />
  );
}

export function WithAvatar() {
  return (
    <Topbar
      user={{
        name: "Joy Adeniran",
        email: "joy@emploihq.com",
        image: "https://api.dicebear.com/7.x/notionists/svg?seed=joy",
      }}
      onMenu={() => {}}
      signOutAction={noOp}
    />
  );
}

export function Anonymous() {
  return (
    <Topbar
      user={{ name: null, email: null, image: null }}
      onMenu={() => {}}
      signOutAction={noOp}
    />
  );
}
