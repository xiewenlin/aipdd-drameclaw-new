import { ArrowRight, ShieldCheck } from "lucide-react";
import {
  requestGulongAuth,
  type GulongAuthMode,
} from "@/lib/gulong-sso";
import styles from "./login.module.css";

type GulongAuthCardProps = {
  mode: GulongAuthMode;
  onSwitchMode: () => void;
};

export function GulongAuthCard({ mode, onSwitchMode }: GulongAuthCardProps) {
  const isLogin = mode === "login";
  return (
    <div className={styles.card}>
      <div style={{ textAlign: "center", marginBottom: "1.25rem" }}>
        <span style={{ display: "inline-grid", placeItems: "center", width: 52, height: 52, borderRadius: 999, marginBottom: 12, color: "var(--color-accent)", background: "color-mix(in srgb, var(--color-accent) 12%, transparent)" }}>
          <ShieldCheck size={28} aria-hidden="true" />
        </span>
        <h3 style={{ margin: "0 0 0.6rem", fontSize: "1.2rem" }}>
          {isLogin ? "使用古龙账号登录" : "注册古龙统一账号"}
        </h3>
        <p style={{ margin: 0, opacity: 0.72, lineHeight: 1.7 }}>
          短剧生产站已接入古龙统一账号。账号、密码、注册与找回功能均由古龙官网安全处理。
        </p>
      </div>
      <button type="button" className={styles.btn} onClick={() => requestGulongAuth(mode)}>
        <span>{isLogin ? "继续登录" : "前往注册"}</span>
        <ArrowRight className={styles.btnArrow} strokeWidth={2.4} aria-hidden="true" />
      </button>
      <div style={{ marginTop: "1rem", textAlign: "center", fontSize: "0.875rem" }}>
        <span style={{ opacity: 0.7 }}>{isLogin ? "还没有古龙账号？" : "已经有古龙账号？"} </span>
        <button type="button" onClick={onSwitchMode} style={{ color: "var(--color-accent)", fontWeight: 600, background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit" }}>
          {isLogin ? "立即注册" : "返回登录"}
        </button>
      </div>
    </div>
  );
}
