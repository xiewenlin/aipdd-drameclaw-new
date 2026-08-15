// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useEffect } from "react";
import { requestGulongAuth } from "@/lib/gulong-sso";

export type AuthModalMode = "login" | "register";

type LoginModalProps = {
  open: boolean;
  onClose: () => void;
  initialMode?: AuthModalMode;
};

export function LoginModal({ open, initialMode = "login" }: LoginModalProps) {
  useEffect(() => {
    if (!open) return;
    requestGulongAuth(initialMode);
  }, [initialMode, open]);

  return null;
}
