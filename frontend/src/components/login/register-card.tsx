// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod/v4";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import styles from "./login.module.css";

const registerSchema = z
  .object({
    username: z.string().min(3, "Username must be at least 3 characters").max(64),
    email: z.string().email("Invalid email").or(z.literal("")),
    password: z.string().min(6, "Password must be at least 6 characters").max(256),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type RegisterForm = z.infer<typeof registerSchema>;

type RegisterCardProps = {
  onSwitchToLogin?: () => void;
};

export function RegisterCard({ onSwitchToLogin }: RegisterCardProps) {
    const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);
  const [showPassword, setShowPassword] = useState(false);
  const usernameRef = useRef<HTMLInputElement | null>(null);
  const passwordRef = useRef<HTMLInputElement | null>(null);

  const {
    register: field,
    handleSubmit,
    formState: { isSubmitting, errors },
    setError,
    clearErrors,
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: { username: "", email: "", password: "", confirmPassword: "" },
  });

  const shake = (el: HTMLInputElement | null) => {
    if (!el) return;
    el.classList.remove(styles.shake);
    void el.offsetWidth;
    el.classList.add(styles.shake);
  };

  const onInvalid = (errs: typeof errors) => {
    if (errs.username) shake(usernameRef.current);
    if (errs.password || errs.confirmPassword) shake(passwordRef.current);
  };

  const onSubmit = async (data: RegisterForm) => {
    try {
      clearErrors();
      await register(data.username, data.password, data.email || undefined);
      toast.success("Account created successfully");
      navigate({ to: "/", replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Registration failed";
      toast.error(message);
      setError("password", { type: "server", message });
      shake(passwordRef.current);
    }
  };

  const { ref: usernameFormRef, ...usernameRest } = field("username");
  const { ref: passwordFormRef, ...passwordRest } = field("password");

  return (
    <div className={styles.card}>
      <form
        noValidate
        className={styles.form}
        onSubmit={handleSubmit(onSubmit, onInvalid)}
      >
        <div className={styles.field}>
          <div className={styles.fieldRow}>
            <label htmlFor="username" className={styles.label}>
              Username
            </label>
          </div>
          <div className={styles.inputWrap}>
            <input
              id="username"
              autoComplete="username"
              placeholder="Choose a username"
              className={`${styles.input} ${errors.username ? styles.inputInvalid : ""}`}
              {...usernameRest}
              ref={(el) => {
                usernameFormRef(el);
                usernameRef.current = el;
              }}
            />
          </div>
          {errors.username && (
            <p className={styles.fieldError}>{errors.username.message}</p>
          )}
        </div>

        <div className={styles.field}>
          <div className={styles.fieldRow}>
            <label htmlFor="email" className={styles.label}>
              Email <span style={{ opacity: 0.5 }}>(optional)</span>
            </label>
          </div>
          <div className={styles.inputWrap}>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="your@email.com"
              className={`${styles.input} ${errors.email ? styles.inputInvalid : ""}`}
              {...field("email")}
            />
          </div>
          {errors.email && (
            <p className={styles.fieldError}>{errors.email.message}</p>
          )}
        </div>

        <div className={styles.field}>
          <div className={styles.fieldRow}>
            <label htmlFor="password" className={styles.label}>
              Password
            </label>
          </div>
          <div className={styles.inputWrap}>
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              placeholder="At least 6 characters"
              className={`${styles.input} ${styles.inputWithEye} ${
                errors.password ? styles.inputInvalid : ""
              }`}
              {...passwordRest}
              ref={(el) => {
                passwordFormRef(el);
                passwordRef.current = el;
              }}
            />
            <button
              type="button"
              className={styles.eyeBtn}
              onClick={() => setShowPassword((v) => !v)}
              tabIndex={-1}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff strokeWidth={2} /> : <Eye strokeWidth={2} />}
            </button>
          </div>
          {errors.password && (
            <p className={styles.fieldError}>{errors.password.message}</p>
          )}
        </div>

        <div className={styles.field}>
          <div className={styles.fieldRow}>
            <label htmlFor="confirmPassword" className={styles.label}>
              Confirm Password
            </label>
          </div>
          <div className={styles.inputWrap}>
            <input
              id="confirmPassword"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              placeholder="Repeat password"
              className={`${styles.input} ${
                errors.confirmPassword ? styles.inputInvalid : ""
              }`}
              {...field("confirmPassword")}
            />
          </div>
          {errors.confirmPassword && (
            <p className={styles.fieldError}>{errors.confirmPassword.message}</p>
          )}
        </div>

        <button
          type="submit"
          className={styles.btn}
          disabled={isSubmitting}
        >
          <span>{isSubmitting ? "Creating account..." : "Create account"}</span>
          <ArrowRight className={styles.btnArrow} strokeWidth={2.4} aria-hidden="true" />
        </button>
      </form>

      <div style={{ marginTop: "1rem", textAlign: "center", fontSize: "0.875rem" }}>
        <span style={{ opacity: 0.7 }}>Already have an account? </span>
        <button
          type="button"
          onClick={onSwitchToLogin}
          style={{ color: "var(--color-accent)", fontWeight: 500, background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit" }}
        >
          Sign in
        </button>
      </div>
    </div>
  );
}
