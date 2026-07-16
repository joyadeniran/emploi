"use client";

import { useEffect } from "react";

export default function ClientRedirectToLogin({
  loginPath = "/login",
}: {
  loginPath?: string;
}) {
  useEffect(() => {
    try {
      const cb = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.replace(`${loginPath}?callbackUrl=${cb}`);
    } catch {
      window.location.replace(loginPath);
    }
  }, [loginPath]);

  return null;
}
