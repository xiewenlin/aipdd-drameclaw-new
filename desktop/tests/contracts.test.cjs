"use strict";

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const {
  OFFICIAL_ORIGIN,
  SHORT_DRAMA_ORIGIN,
  buildH3TaskPayload,
  classifyNavigation,
  normalizeAuthMode,
} = require("../src/contracts.cjs");

test("builds the exact Gulong H3 desktop task contract", () => {
  assert.deepEqual(buildH3TaskPayload({ prompt: "  雨夜追车  ", durationSeconds: 8, aspectRatio: "9:16" }), {
    source_channel: "desktop_agent",
    model: "minimax_h3_shared",
    prompt: "雨夜追车",
    aspect_ratio: "9:16",
    duration_seconds: 8,
    profile: "balanced",
    assets: { images: [], videos: [], audio: [] },
  });
});

test("rejects invalid prompt and duration before a billable request", () => {
  assert.throws(() => buildH3TaskPayload({ prompt: "", durationSeconds: 5 }), /提示词/);
  assert.throws(() => buildH3TaskPayload({ prompt: "镜头", durationSeconds: 0 }), /时长/);
  assert.throws(() => buildH3TaskPayload({ prompt: "镜头", durationSeconds: 601 }), /时长/);
});

test("only keeps known aspect ratios", () => {
  assert.equal(buildH3TaskPayload({ prompt: "镜头", durationSeconds: 5, aspectRatio: "javascript:" }).aspect_ratio, "9:16");
});

test("navigation is constrained to the short-drama app and trusted HTTPS destinations", () => {
  assert.equal(classifyNavigation(`${SHORT_DRAMA_ORIGIN}/projects`).action, "allow");
  assert.deepEqual(classifyNavigation(`${OFFICIAL_ORIGIN}/short-drama?auth=register`).action, "official");
  assert.equal(classifyNavigation("https://example.com/help").action, "external");
  assert.equal(classifyNavigation("file:///C:/Windows/System32/config").action, "block");
  assert.equal(classifyNavigation("javascript:alert(1)").action, "block");
});

test("unknown auth modes never escape the login flow", () => {
  assert.equal(normalizeAuthMode("register"), "register");
  assert.equal(normalizeAuthMode("admin"), "login");
});

test("desktop dialogs leave the toolbar outside their mask", () => {
  const rendererSource = readFileSync(path.join(__dirname, "../renderer/app.js"), "utf8");
  const styleSource = readFileSync(path.join(__dirname, "../renderer/styles.css"), "utf8");
  const mainSource = readFileSync(path.join(__dirname, "../src/main.cjs"), "utf8");

  assert.doesNotMatch(rendererSource, /showModal\(/);
  assert.match(rendererSource, /dialog\.show\(\)/);
  assert.match(rendererSource, /setOverlayVisible\(true\)/);
  assert.match(styleSource, /\.desktop-toolbar\s*\{[^}]*z-index:\s*1000/s);
  assert.match(styleSource, /\.dialog-shade\s*\{[^}]*inset:\s*68px 0 0/s);
  assert.match(mainSource, /overlayVisible[\s\S]*width:\s*0,\s*height:\s*0/);
});
