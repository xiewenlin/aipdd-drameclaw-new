// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { LoginCard } from "./login-card";
import { RegisterCard } from "./register-card";
import styles from "./login.module.css";

export type AuthModalMode = "login" | "register";

type LoginModalProps = {
  open: boolean;
  onClose: () => void;
  initialMode?: AuthModalMode;
};

export function LoginModal({ open, onClose, initialMode = "login" }: LoginModalProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<AuthModalMode>(initialMode);

  useEffect(() => {
    if (open) {
      setMode(initialMode);
    }
  }, [open, initialMode]);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className={styles.loginOverlay}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          role="dialog"
          aria-modal="true"
          aria-label={mode === "login" ? t("auth.login") : t("auth.register") || "Sign up"}
        >
          <motion.div
            className={styles.loginDialog}
            initial={{ opacity: 0, scale: 0.98, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 10 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <button
              type="button"
              className={styles.loginClose}
              onClick={onClose}
              aria-label={t("auth.closeLogin")}
            >
              <X strokeWidth={1.8} aria-hidden="true" />
            </button>
            <div className={styles.authTabs}>
              <button
                type="button"
                className={`${styles.authTab} ${mode === "login" ? styles.authTabActive : ""}`}
                onClick={() => setMode("login")}
              >
                {t("auth.login")}
              </button>
              <button
                type="button"
                className={`${styles.authTab} ${mode === "register" ? styles.authTabActive : ""}`}
                onClick={() => setMode("register")}
              >
                {t("auth.register") || "Sign up"}
              </button>
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={mode}
                initial={{ opacity: 0, x: mode === "login" ? -12 : 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: mode === "login" ? 12 : -12 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {mode === "login" ? (
                  <LoginCard onSwitchToRegister={() => setMode("register")} />
                ) : (
                  <RegisterCard onSwitchToLogin={() => setMode("login")} />
                )}
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}