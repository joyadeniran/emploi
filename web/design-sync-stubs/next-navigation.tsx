export function useRouter() {
  return {
    push: (_url: string) => {},
    replace: (_url: string) => {},
    back: () => {},
    forward: () => {},
    refresh: () => {},
    prefetch: (_url: string) => {},
  };
}

export function usePathname(): string {
  return "/";
}

export function useSearchParams() {
  return new URLSearchParams();
}

export function redirect(_url: string): never {
  throw new Error("redirect() called in design-sync stub");
}

export function notFound(): never {
  throw new Error("notFound() called in design-sync stub");
}
