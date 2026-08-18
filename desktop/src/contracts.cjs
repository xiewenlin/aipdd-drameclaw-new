"use strict";

const OFFICIAL_ORIGIN = "https://sologle.com";
const SHORT_DRAMA_ORIGIN = "https://aipdd-drameclaw-new.vercel.app";
const ALLOWED_ASPECT_RATIOS = new Set(["9:16", "16:9", "1:1", "4:3", "3:4"]);

function integer(value, fallback = -1) {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : fallback;
}

function normalizeAuthMode(value) {
  return value === "register" ? "register" : "login";
}

function buildH3TaskPayload(input = {}) {
  const prompt = String(input.prompt || "").trim();
  const durationSeconds = integer(input.durationSeconds ?? input.duration_seconds);
  const aspectRatio = ALLOWED_ASPECT_RATIOS.has(String(input.aspectRatio || input.aspect_ratio))
    ? String(input.aspectRatio || input.aspect_ratio)
    : "9:16";
  if (!prompt || prompt.length > 20_000) {
    throw Object.assign(new Error("提示词需为 1–20000 个字符"), { code: "VALIDATION_ERROR" });
  }
  if (durationSeconds < 1 || durationSeconds > 600) {
    throw Object.assign(new Error("视频时长需为 1–600 秒"), { code: "VALIDATION_ERROR" });
  }
  return {
    source_channel: "desktop_agent",
    model: "minimax_h3_shared",
    prompt,
    aspect_ratio: aspectRatio,
    duration_seconds: durationSeconds,
    profile: "balanced",
    assets: { images: [], videos: [], audio: [] },
  };
}

function createIdempotencyKey() {
  return `dramaclaw-desktop-${Date.now()}-${crypto.randomUUID()}`;
}

function classifyNavigation(rawUrl) {
  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    return { action: "block" };
  }
  if (url.origin === SHORT_DRAMA_ORIGIN) return { action: "allow", url: url.toString() };
  if (url.origin === OFFICIAL_ORIGIN || url.origin === "https://www.sologle.com") {
    const mode = url.searchParams.get("auth") === "register" || url.searchParams.get("mode") === "register"
      ? "register"
      : "login";
    return { action: "official", url: url.toString(), mode };
  }
  if (url.protocol === "https:" || url.protocol === "mailto:") {
    return { action: "external", url: url.toString() };
  }
  return { action: "block" };
}

module.exports = {
  OFFICIAL_ORIGIN,
  SHORT_DRAMA_ORIGIN,
  buildH3TaskPayload,
  classifyNavigation,
  createIdempotencyKey,
  normalizeAuthMode,
};
