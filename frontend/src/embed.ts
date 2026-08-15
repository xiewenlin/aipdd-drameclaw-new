import "./embed.css";

const GULONG_ORIGIN = (
  import.meta.env.VITE_GULONG_ORIGIN || "https://sologle.com"
).replace(/\/$/, "");

const startButton = document.querySelector<HTMLButtonElement>("#start-create")!;
const watchButton = document.querySelector<HTMLButtonElement>("#watch-now")!;
const dialog = document.querySelector<HTMLElement>("#watch-dialog")!;
const closeButton = document.querySelector<HTMLButtonElement>("#close-player")!;
const player = document.querySelector<HTMLVideoElement>("#preview-player")!;
const accountStatus = document.querySelector<HTMLElement>("#account-status")!;

let sessionReady = false;
let enterAfterExchange = false;
let exchangeInFlight: Promise<void> | null = null;

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
  if (sessionReady) {
    window.location.assign("/");
    return;
  }
  enterAfterExchange = true;
  accountStatus.textContent = "等待账号授权…";
  window.parent.postMessage(
    { type: "dramaclaw:auth-request", mode: "login" },
    GULONG_ORIGIN,
  );
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
      accountStatus.textContent = "创作空间已就绪";
      if (enterAfterExchange) window.location.assign("/");
    } catch (error) {
      const message = error instanceof Error ? error.message : "古龙账号授权失败";
      accountStatus.textContent = "";
      enterAfterExchange = false;
      window.parent.postMessage(
        { type: "dramaclaw:sso-error", message },
        GULONG_ORIGIN,
      );
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
  if (event.origin !== GULONG_ORIGIN || event.source !== window.parent) return;
  if (event.data?.type !== "gulong:sso" || typeof event.data.token !== "string") return;
  void exchangeAssertion(event.data.token);
});

if (window.parent !== window) {
  window.parent.postMessage({ type: "dramaclaw:ready" }, GULONG_ORIGIN);
}
