export function useRouter() {
  return {
    push: (url: string) => { void url; },
    replace: (url: string) => { void url; },
    back: () => {},
    forward: () => {},
    refresh: () => {},
    prefetch: (url: string) => { void url; },
  };
}

export function usePathname(): string {
  return "/";
}

export function useSearchParams() {
  return new URLSearchParams();
}

export function redirect(url: string): never {
  void url;
  throw new Error("redirect() called in design-sync stub");
}

export function notFound(): never {
  throw new Error("notFound() called in design-sync stub");
}
