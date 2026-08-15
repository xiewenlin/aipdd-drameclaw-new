const DEFAULT_GULONG_ORIGIN = "https://sologle.com";

function parseOrigin(value: string): string | null {
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

export const GULONG_ORIGIN =
  parseOrigin(import.meta.env.VITE_GULONG_ORIGIN || DEFAULT_GULONG_ORIGIN) ??
  DEFAULT_GULONG_ORIGIN;

function getCompanionOrigin(origin: string): string | null {
  try {
    const url = new URL(origin);
    url.hostname = url.hostname.startsWith("www.")
      ? url.hostname.slice(4)
      : "www." + url.hostname;
    return url.origin;
  } catch {
    return null;
  }
}

const companionOrigin = getCompanionOrigin(GULONG_ORIGIN);
const allowedOrigins = new Set(
  companionOrigin ? [GULONG_ORIGIN, companionOrigin] : [GULONG_ORIGIN],
);

export function isAllowedGulongOrigin(origin: string): boolean {
  const normalized = parseOrigin(origin);
  return normalized !== null && allowedOrigins.has(normalized);
}

export function resolveGulongParentOrigin(referrer?: string): string {
  const source = referrer ?? (typeof document === "undefined" ? "" : document.referrer);
  try {
    const origin = new URL(source).origin;
    if (isAllowedGulongOrigin(origin)) return origin;
  } catch {
    // Missing or malformed referrer: fall back to the configured canonical origin.
  }
  return GULONG_ORIGIN;
}
