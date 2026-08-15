// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { createFileRoute, redirect } from "@tanstack/react-router";
import { useEffect } from "react";
import { LoginCinematicPage } from "@/components/login/cinematic/LoginCinematicPage";
import { useAuthStore } from "@/stores/auth-store";
import { ensureAuthenticatedForAppRoute } from "@/lib/auth-mode";
import { clusterConfig } from "@/lib/cluster-config";
import { getRegionCookie } from "@/lib/region-cookie";
import { authRequired } from "@/lib/runtime-config";
import { requestGulongAuth, type GulongAuthMode } from "@/lib/gulong-sso";

function GulongAuthHandoff() {
  const mode: GulongAuthMode = new URLSearchParams(window.location.search).get("mode") === "register"
    ? "register"
    : "login";

  useEffect(() => {
    requestGulongAuth(mode);
  }, [mode]);

  return (
    <main className="flex h-dvh items-center justify-center bg-background px-6 text-foreground" aria-live="polite">
      <p className="text-sm text-muted-foreground">正在连接古龙官网账号…</p>
    </main>
  );
}

function LoginPage() {
  if (clusterConfig.mode === "multi-region" && !getRegionCookie()) {
    return <LoginCinematicPage />;
  }
  return <GulongAuthHandoff />;
}

export const Route = createFileRoute("/login")({
  beforeLoad: async () => {
    // In multi-region mode, if region cookie is missing, stay on /login —
    // user must re-pick a region. Also clear the stale persisted username
    // so the picker can gate the submit button cleanly.
    if (clusterConfig.mode === "multi-region" && !getRegionCookie()) {
      useAuthStore.getState().reset();
      return;
    }

    if (!authRequired()) {
      throw redirect({ to: "/", replace: true });
    }
    if (!(await ensureAuthenticatedForAppRoute())) return; // stay on /login

    throw redirect({ to: "/", replace: true });
  },
  component: LoginPage,
});
