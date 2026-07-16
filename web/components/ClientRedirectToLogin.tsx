"use client";

import { useEffect } from "react";

export default function ClientRedirectToLogin() {
  useEffect(() => {
    try {
      const cb = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.replace(`/login?callbackUrl=${cb}`);
    } catch {
      window.location.replace(`/login`);
    }
  }, []);

  return null;
}
