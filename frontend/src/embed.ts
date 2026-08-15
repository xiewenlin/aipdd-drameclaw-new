import "./embed.css";
import {
  GULONG_ORIGIN,
  isAllowedGulongOrigin,
  resolveGulongParentOrigin,
} from "./lib/gulong-origin";

const gulongParentOrigin = resolveGulongParentOrigin();

const startButton = document.querySelector<HTMLButtonElement>("#start-create")!;
const watchButton = document.querySelector<HTMLButtonElement>("#watch-now")!;
const dialog = document.querySelector<HTMLElement>("#watch-dialog")!;
const closeButton = document.querySelector<HTMLButtonElement>("#close-player")!;
const player = document.querySelector<HTMLVideoElement>("#preview-player")!;
const accountStatus = document.querySelector<HTMLElement>("#account-status")!;

let sessionReady = false;
let enterAfterExchange = false;
let exchangeInFlight: Promise<void> | null = null;
let pendingFeedbackTimer: number | null = null;

function setStartButton(label: string, busy = false): void {
  startButton.textContent = label;
  if (busy) startButton.setAttribute("aria-busy", "true");
  else startButton.removeAttribute("aria-busy");
}

function postToGulong(message: Record<string, unknown>): void {
  if (window.parent === window) return;
  window.parent.postMessage(message, gulongParentOrigin);
}

function openPlayer(): void {
  if (!player.src) player.src = player.dataset.src || "";
  dialog.hidden = false;
  document.body.classList.add("player-open");
  closeButton.focus();
  void player.play().catch(() => {});
}

function closePlayer(): void {
  player.pause();
  dialog.hidden = true;
  document.body.classList.remove("player-open");
  watchButton.focus();
}

function enterStudio(): void {
  if (window.parent === window) {
    window.location.assign(`${GULONG_ORIGIN}/short-drama?auth=login`);
    return;
  }
  if (sessionReady) {
    window.location.assign("/");
    return;
  }
  enterAfterExchange = true;
  accountStatus.textContent = "等待账号授权…";
  setStartButton("正在进入…", true);
  postToGulong({ type: "dramaclaw:auth-request", mode: "login" });
  window.clearTimeout(pendingFeedbackTimer ?? undefined);
  pendingFeedbackTimer = window.setTimeout(() => {
    if (sessionReady || exchangeInFlight) return;
    setStartButton("重新尝试");
    accountStatus.textContent = "请在古龙登录窗口完成登录";
  }, 8000);
}

async function exchangeAssertion(token: string): Promise<void> {
  if (exchangeInFlight) return exchangeInFlight;
  exchangeInFlight = (async () => {
    accountStatus.textContent = "正在连接创作空间…";
    try {
      const response = await fetch("/api/v1/auth/gulong/exchange", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "古龙账号授权失败");
      }
      sessionReady = true;
      window.clearTimeout(pendingFeedbackTimer ?? undefined);
      accountStatus.textContent = "创作空间已就绪";
      setStartButton(enterAfterExchange ? "正在进入…" : "进入创作空间", enterAfterExchange);
      if (enterAfterExchange) window.location.assign("/");
    } catch (error) {
      const message = error instanceof Error ? error.message : "古龙账号授权失败";
      accountStatus.textContent = "";
      enterAfterExchange = false;
      setStartButton("重新尝试");
      postToGulong({ type: "dramaclaw:sso-error", message });
    } finally {
      exchangeInFlight = null;
    }
  })();
  return exchangeInFlight;
}

watchButton.addEventListener("click", openPlayer);
closeButton.addEventListener("click", closePlayer);
startButton.addEventListener("click", enterStudio);
dialog.addEventListener("click", (event) => {
  if (event.target === dialog) closePlayer();
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !dialog.hidden) closePlayer();
});
window.addEventListener("message", (event) => {
  if (!isAllowedGulongOrigin(event.origin) || event.source !== window.parent) return;
  if (event.data?.type !== "gulong:sso" || typeof event.data.token !== "string") return;
  void exchangeAssertion(event.data.token);
});

if (window.parent !== window) {
  postToGulong({ type: "dramaclaw:ready" });
}
