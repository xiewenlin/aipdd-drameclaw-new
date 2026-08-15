import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/auth-store";
import {
  GULONG_ORIGIN,
  isAllowedGulongOrigin,
  resolveGulongParentOrigin,
} from "@/lib/gulong-origin";

export { GULONG_ORIGIN } from "@/lib/gulong-origin";

export type GulongAuthMode = "login" | "register";

export function isEmbeddedInGulong(): boolean {
  return typeof window !== "undefined" && window.parent !== window;
}

export function requestGulongAuth(mode: GulongAuthMode): void {
  if (isEmbeddedInGulong()) {
    window.parent.postMessage(
      { type: "dramaclaw:auth-request", mode },
      resolveGulongParentOrigin(),
    );
    return;
  }
  window.location.assign(`${GULONG_ORIGIN}/short-drama?auth=${mode}`);
}

/** Exchange a one-use assertion from the embedding Gulong page for a session. */
export function useGulongSsoBridge(): void {
  const exchanging = useRef(false);

  useEffect(() => {
    if (!isEmbeddedInGulong()) return;
    const parentOrigin = resolveGulongParentOrigin();

    const receiveAssertion = async (event: MessageEvent) => {
      if (!isAllowedGulongOrigin(event.origin) || event.source !== window.parent) return;
      if (event.data?.type !== "gulong:sso" || typeof event.data.token !== "string") return;
      if (exchanging.current) return;
      exchanging.current = true;
      try {
        const response = await fetch("/api/v1/auth/gulong/exchange", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ token: event.data.token }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail || "古龙账号授权失败");
        }
        const user = await useAuthStore.getState().getCurrentUser({
          clearOnNetworkFailure: false,
        });
        if (!user) throw new Error("古龙账号会话未生效");
        const target = window.location.pathname === "/login"
          ? "/"
          : `${window.location.pathname}${window.location.search}${window.location.hash}`;
        window.location.replace(target);
      } catch (error) {
        exchanging.current = false;
        const message = error instanceof Error ? error.message : "古龙账号授权失败";
        toast.error(message);
        window.parent.postMessage(
          { type: "dramaclaw:sso-error", message },
          parentOrigin,
        );
      }
    };

    window.addEventListener("message", receiveAssertion);
    if (window.location.pathname === "/login") {
      window.parent.postMessage({ type: "dramaclaw:ready" }, parentOrigin);
    }
    return () => window.removeEventListener("message", receiveAssertion);
  }, []);
}
