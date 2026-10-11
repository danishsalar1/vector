import { useSyncExternalStore } from "react";

/**
 * Tracks a CSS media query. Returns false where matchMedia is unavailable (SSR, jsdom),
 * which keeps the full, un-collapsed layout.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = (onChange: () => void) => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return () => {};
    }
    const mql = window.matchMedia(query);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  };
  const snapshot = () =>
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(query).matches;
  return useSyncExternalStore(subscribe, snapshot, () => false);
}

/** Phone-width layout: long explanatory text is collapsed behind a disclosure. */
export const NARROW_QUERY = "(max-width: 680px)";
