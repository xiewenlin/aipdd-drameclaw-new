"use strict";

const byId = (id) => document.getElementById(id);
const money = (fen) => `¥${(Number(fen || 0) / 100).toFixed(2)}`;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);

const status = document.querySelector(".status");
const statusText = byId("status-text");
const authActions = byId("auth-actions");
const identity = byId("identity");
const taskDialog = byId("task-dialog");
const resultDialog = byId("result-dialog");
const listDialog = byId("list-dialog");
const dialogShade = byId("dialog-shade");
const taskError = byId("task-error");
const resultRecharge = byId("result-recharge");
let activeDialog = null;

async function closeActiveDialog() {
  if (activeDialog?.open) activeDialog.close();
  activeDialog = null;
  dialogShade.hidden = true;
  await window.gulongShell.setOverlayVisible(false);
}

async function openDialog(dialog) {
  if (activeDialog && activeDialog !== dialog && activeDialog.open) activeDialog.close();
  activeDialog = dialog;
  dialogShade.hidden = false;
  if (!dialog.open) dialog.show();
  await window.gulongShell.setOverlayVisible(true);
}

function renderState(state) {
  status.classList.toggle("loading", Boolean(state.loading));
  statusText.textContent = state.message || "古龙短剧工作台";
  const account = state.account || {};
  authActions.hidden = Boolean(account.authenticated);
  identity.hidden = !account.authenticated;
  if (account.authenticated && account.user) {
    const name = account.user.displayName || account.user.username || account.user.email || "古龙用户";
    byId("identity-mark").textContent = name.slice(0, 1).toUpperCase();
    byId("identity-name").textContent = name;
    byId("identity-balance").textContent = money(account.balanceFen);
    identity.title = account.isMember ? "古龙会员 · 打开用户中心" : "普通用户 · 打开用户中心";
  }
}

async function showResult({ success, title, eyebrow, content, recharge = false }) {
  byId("result-title").textContent = title;
  byId("result-eyebrow").textContent = eyebrow;
  byId("result-content").innerHTML = content;
  resultRecharge.hidden = !recharge;
  resultDialog.dataset.success = success ? "true" : "false";
  await openDialog(resultDialog);
}

async function openOfficial(page) {
  await closeActiveDialog();
  const result = await window.gulongShell.openOfficialPage(page);
  if (!result.ok) await showResult({ success: false, title: "无法打开古龙官网", eyebrow: result.code || "ERROR", content: `<p>${escapeHtml(result.message)}</p>` });
}

document.querySelectorAll("[data-nav]").forEach((button) => button.addEventListener("click", async () => { await closeActiveDialog(); await window.gulongShell.navigate(button.dataset.nav); }));
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", closeActiveDialog));
dialogShade.addEventListener("click", closeActiveDialog);
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && activeDialog) void closeActiveDialog(); });
byId("login").addEventListener("click", async () => { await closeActiveDialog(); await window.gulongShell.authenticate("login"); });
byId("register").addEventListener("click", async () => { await closeActiveDialog(); await window.gulongShell.authenticate("register"); });
byId("account").addEventListener("click", () => openOfficial("account"));
identity.addEventListener("click", () => openOfficial("account"));
byId("subscription").addEventListener("click", () => openOfficial("subscription"));
byId("recharge").addEventListener("click", () => openOfficial("recharge"));
resultRecharge.addEventListener("click", () => openOfficial("recharge"));

byId("new-task").addEventListener("click", async () => {
  taskError.hidden = true;
  await openDialog(taskDialog);
  byId("task-prompt").focus();
});

byId("task-duration").addEventListener("input", (event) => {
  const seconds = Math.max(0, Number(event.target.value || 0));
  byId("estimated-price").textContent = money(seconds * 20);
});

byId("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  taskError.hidden = true;
  const submit = byId("submit-task");
  submit.disabled = true;
  submit.textContent = "正在提交…";
  const result = await window.gulongShell.createVideoTask({
    prompt: byId("task-prompt").value,
    durationSeconds: Number(byId("task-duration").value),
    aspectRatio: byId("task-ratio").value,
  });
  submit.disabled = false;
  submit.textContent = "提交生成任务";
  if (!result.ok) {
    if (result.code === "INSUFFICIENT_BALANCE") {
      await closeActiveDialog();
      await showResult({ success: false, title: "账户余额不足", eyebrow: "INSUFFICIENT BALANCE", recharge: true, content: `<p>${escapeHtml(result.message)}</p>` });
      return;
    }
    taskError.textContent = result.message || "任务提交失败";
    taskError.hidden = false;
    return;
  }
  await closeActiveDialog();
  byId("task-form").reset();
  byId("estimated-price").textContent = money(100);
  const task = result.task || {};
  const billing = result.billing || {};
  await showResult({
    success: true,
    title: "视频任务已进入队列",
    eyebrow: "TASK CREATED",
    content: `<dl><div><dt>订单号</dt><dd>${escapeHtml(task.orderNo || task.id)}</dd></div><div><dt>状态</dt><dd>${escapeHtml(task.status || "queued")}</dd></div><div><dt>本次扣费</dt><dd>${money(billing.chargedFen ?? task.priceFen)}</dd></div><div><dt>剩余余额</dt><dd>${money(billing.remainingBalanceFen)}</dd></div></dl>`,
  });
});

function taskStatusLabel(statusValue) {
  return ({ queued: "排队中", claimed: "生成中", processing: "生成中", completed: "已完成", failed: "失败", cancelled: "已取消", rejected: "未扣费" })[statusValue] || statusValue || "未知";
}

async function loadTasks() {
  const container = byId("task-items");
  container.innerHTML = '<div class="empty">正在读取古龙官网任务…</div>';
  const result = await window.gulongShell.listVideoTasks();
  if (!result.ok) {
    container.innerHTML = `<div class="empty">${escapeHtml(result.message)}</div>`;
    return;
  }
  if (!result.tasks.length) {
    container.innerHTML = '<div class="empty">还没有视频生成任务</div>';
    return;
  }
  container.innerHTML = result.tasks.map((task) => `<article class="task-card"><strong>${escapeHtml(task.orderNo || task.id)}</strong><em>${escapeHtml(taskStatusLabel(task.status))}</em><p>${escapeHtml(task.prompt || "")}</p><small>${escapeHtml(task.aspectRatio || "9:16")} · ${Number(task.durationSeconds || 0)} 秒 · ${money(task.priceFen)}</small><small>${escapeHtml(task.createdAt ? new Date(task.createdAt).toLocaleString("zh-CN") : "")}</small></article>`).join("");
}

byId("task-list").addEventListener("click", async () => { await openDialog(listDialog); void loadTasks(); });
byId("refresh-tasks").addEventListener("click", loadTasks);

window.gulongShell.onState(renderState);
window.gulongShell.getState().then(renderState);
