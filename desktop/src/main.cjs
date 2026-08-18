"use strict";

const path = require("node:path");
const {
  app,
  BrowserView,
  BrowserWindow,
  ipcMain,
  Menu,
  shell,
} = require("electron");
const {
  OFFICIAL_ORIGIN,
  SHORT_DRAMA_ORIGIN,
  buildH3TaskPayload,
  classifyNavigation,
  createIdempotencyKey,
  normalizeAuthMode,
} = require("./contracts.cjs");

const TOOLBAR_HEIGHT = 68;
const OFFICIAL_PARTITION = "persist:gulong-account";
const SHORT_DRAMA_PARTITION = "persist:gulong-short-drama";
const OFFICIAL_PAGES = {
  account: "/account",
  subscription: "/pricing",
  recharge: "/pricing#recharge",
  tasks: "/account",
};

let mainWindow = null;
let contentView = null;
let officialServiceWindow = null;
const officialPageWindows = new Set();
let authInFlight = null;

let desktopState = {
  loading: true,
  message: "正在连接古龙短剧工作台…",
  contentUrl: `${SHORT_DRAMA_ORIGIN}/`,
  account: {
    authenticated: false,
    user: null,
    balanceFen: 0,
    isMember: false,
    subscription: null,
  },
};

function serializeError(error, fallback = "操作失败，请稍后重试") {
  return {
    ok: false,
    code: error?.code || "DESKTOP_ERROR",
    status: Number(error?.status || 0),
    message: error?.message || fallback,
    details: error?.details || null,
  };
}

function publishState(patch = {}) {
  desktopState = {
    ...desktopState,
    ...patch,
    account: patch.account ? { ...desktopState.account, ...patch.account } : desktopState.account,
  };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("desktop:state", desktopState);
  }
}

function resizeContentView() {
  if (!mainWindow || mainWindow.isDestroyed() || !contentView) return;
  const [width, height] = mainWindow.getContentSize();
  contentView.setBounds({ x: 0, y: TOOLBAR_HEIGHT, width, height: Math.max(0, height - TOOLBAR_HEIGHT) });
  contentView.setAutoResize({ width: true, height: true });
}

function waitForLoad(webContents) {
  if (!webContents.isLoadingMainFrame()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const completed = () => { cleanup(); resolve(); };
    const failed = (_event, code, description, url, isMainFrame) => {
      if (!isMainFrame) return;
      cleanup();
      reject(Object.assign(new Error(`页面加载失败：${description}`), { code: "PAGE_LOAD_FAILED", details: { code, url } }));
    };
    const cleanup = () => {
      webContents.removeListener("did-finish-load", completed);
      webContents.removeListener("did-fail-load", failed);
    };
    webContents.once("did-finish-load", completed);
    webContents.on("did-fail-load", failed);
  });
}

async function executeJsonFetch(webContents, pathname, options = {}) {
  if (webContents.isDestroyed()) throw new Error("古龙官网账号窗口已关闭");
  const script = `(() => fetch(${JSON.stringify(pathname)}, {
    method: ${JSON.stringify(options.method || "GET")},
    credentials: "include",
    headers: ${JSON.stringify(options.headers || {})},
    ${options.body === undefined ? "" : `body: ${JSON.stringify(JSON.stringify(options.body))},`}
  }).then(async (response) => {
    const text = await response.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = { message: text }; }
    return { ok: response.ok, status: response.status, body };
  }))()`;
  return webContents.executeJavaScript(script, true);
}

async function ensureOfficialServiceWindow() {
  if (officialServiceWindow && !officialServiceWindow.isDestroyed()) {
    await waitForLoad(officialServiceWindow.webContents);
    return officialServiceWindow;
  }
  officialServiceWindow = new BrowserWindow({
    width: 1080,
    height: 780,
    minWidth: 760,
    minHeight: 620,
    parent: mainWindow || undefined,
    show: false,
    title: "古龙账号",
    autoHideMenuBar: true,
    backgroundColor: "#f7f5ef",
    webPreferences: {
      partition: OFFICIAL_PARTITION,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  officialServiceWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });
  officialServiceWindow.on("closed", () => { officialServiceWindow = null; });
  await officialServiceWindow.loadURL(`${OFFICIAL_ORIGIN}/`);
  return officialServiceWindow;
}

async function officialFetch(pathname, options) {
  const win = await ensureOfficialServiceWindow();
  return executeJsonFetch(win.webContents, pathname, options);
}

async function readOfficialAccount() {
  const me = await officialFetch("/api/auth/me");
  if (!me.ok || !me.body?.user) {
    publishState({
      loading: false,
      message: "请登录古龙账号后继续",
      account: { authenticated: false, user: null, balanceFen: 0, isMember: false, subscription: null },
    });
    return null;
  }
  const [billing, dashboard] = await Promise.all([
    officialFetch("/api/billing/subscription"),
    officialFetch("/api/account/dashboard"),
  ]);
  const account = {
    authenticated: true,
    user: me.body.user,
    balanceFen: Number(dashboard.body?.balanceFen || billing.body?.balanceFen || 0),
    isMember: Boolean(billing.body?.isMember || billing.body?.subscription?.status === "active"),
    subscription: billing.body?.subscription || null,
  };
  publishState({ loading: false, message: `已连接：${account.user.displayName || account.user.username || account.user.email}`, account });
  return account;
}

async function openOfficialAuthModal(win, mode) {
  const script = `(() => {
    const click = (selector, text) => {
      const nodes = [...document.querySelectorAll(selector)];
      const target = text ? nodes.find((node) => node.textContent.trim() === text) : nodes[0];
      if (target) { target.click(); return true; }
      return false;
    };
    click("button.login-button");
    setTimeout(() => click(".account-tabs button", ${JSON.stringify(mode === "register" ? "注册" : "登录")}), 120);
    return true;
  })()`;
  await win.webContents.executeJavaScript(script, true);
}

function waitForOfficialLogin(win, mode) {
  return new Promise((resolve, reject) => {
    let busy = false;
    const timer = setInterval(async () => {
      if (busy) return;
      if (!win || win.isDestroyed()) {
        clearInterval(timer);
        reject(Object.assign(new Error(mode === "register" ? "注册窗口已关闭" : "登录窗口已关闭"), { code: "AUTH_CANCELLED" }));
        return;
      }
      busy = true;
      try {
        const response = await executeJsonFetch(win.webContents, "/api/auth/me");
        if (response.ok && response.body?.user) {
          clearInterval(timer);
          resolve(response.body.user);
        }
      } catch {
        // Navigation or a transient page reload is expected while the form submits.
      } finally {
        busy = false;
      }
    }, 900);
  });
}

async function exchangeShortDramaSession() {
  const assertion = await officialFetch("/api/auth/short-drama-sso", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: {},
  });
  if (!assertion.ok || !assertion.body?.token) {
    throw Object.assign(new Error(assertion.body?.message || "无法获取古龙短剧授权"), { code: assertion.body?.code || "SSO_ASSERTION_FAILED", status: assertion.status });
  }
  if (!contentView || contentView.webContents.isDestroyed()) throw new Error("短剧工作台尚未就绪");
  const current = new URL(contentView.webContents.getURL() || `${SHORT_DRAMA_ORIGIN}/`);
  if (current.origin !== SHORT_DRAMA_ORIGIN) {
    await contentView.webContents.loadURL(`${SHORT_DRAMA_ORIGIN}/login?desktop=1`);
  }
  const response = await contentView.webContents.session.fetch(`${SHORT_DRAMA_ORIGIN}/api/v1/auth/gulong/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ token: assertion.body.token }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw Object.assign(new Error(body?.detail || "古龙账号未能登录短剧工作台"), { code: "SHORT_DRAMA_EXCHANGE_FAILED", status: response.status });
  }
  await contentView.webContents.loadURL(`${SHORT_DRAMA_ORIGIN}/`);
  return body;
}

async function authenticate(modeValue = "login") {
  if (authInFlight) return authInFlight;
  const mode = normalizeAuthMode(modeValue);
  authInFlight = (async () => {
    publishState({ loading: true, message: mode === "register" ? "正在打开古龙注册…" : "正在连接古龙登录…" });
    const win = await ensureOfficialServiceWindow();
    let me = await executeJsonFetch(win.webContents, "/api/auth/me");
    if (!me.ok || !me.body?.user) {
      await openOfficialAuthModal(win, mode);
      win.show();
      win.focus();
      await waitForOfficialLogin(win, mode);
    }
    win.hide();
    await exchangeShortDramaSession();
    const account = await readOfficialAccount();
    return { ok: true, account };
  })().catch((error) => {
    publishState({ loading: false, message: error.message || "古龙账号连接失败" });
    return serializeError(error, "古龙账号连接失败");
  }).finally(() => { authInFlight = null; });
  return authInFlight;
}

async function ensureAuthenticated() {
  const account = await readOfficialAccount().catch(() => null);
  if (account) return account;
  const result = await authenticate("login");
  if (!result.ok) throw Object.assign(new Error(result.message), result);
  return result.account;
}

async function openOfficialPage(page) {
  await ensureAuthenticated();
  const pathname = OFFICIAL_PAGES[page];
  if (!pathname) throw Object.assign(new Error("不支持的古龙官网页面"), { code: "PAGE_NOT_ALLOWED" });
  const win = new BrowserWindow({
    width: 1160,
    height: 820,
    minWidth: 820,
    minHeight: 640,
    parent: mainWindow || undefined,
    title: page === "recharge" ? "古龙充值" : page === "subscription" ? "古龙会员订阅" : "古龙用户中心",
    autoHideMenuBar: true,
    backgroundColor: "#f7f5ef",
    webPreferences: { partition: OFFICIAL_PARTITION, contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });
  officialPageWindows.add(win);
  win.on("closed", () => officialPageWindows.delete(win));
  await win.loadURL(`${OFFICIAL_ORIGIN}${pathname}`);
  return { ok: true };
}

async function createVideoTask(input) {
  try {
    await ensureAuthenticated();
    const payload = buildH3TaskPayload(input);
    const request = {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": createIdempotencyKey() },
      body: payload,
    };
    let response = await officialFetch("/api/h3/tasks", request);
    if (response.status === 401) {
      const auth = await authenticate("login");
      if (!auth.ok) return auth;
      response = await officialFetch("/api/h3/tasks", request);
    }
    if (!response.ok) {
      throw Object.assign(new Error(response.body?.message || "官网未能创建视频任务"), {
        code: response.body?.code || "TASK_CREATE_FAILED",
        status: response.status,
        details: response.body,
      });
    }
    await readOfficialAccount().catch(() => null);
    return { ok: true, ...response.body };
  } catch (error) {
    return serializeError(error, "官网未能创建视频任务");
  }
}

async function listVideoTasks() {
  try {
    await ensureAuthenticated();
    const response = await officialFetch("/api/h3/tasks");
    if (!response.ok) throw Object.assign(new Error(response.body?.message || "无法读取视频任务"), { code: response.body?.code, status: response.status });
    return { ok: true, tasks: response.body?.tasks || [] };
  } catch (error) {
    return serializeError(error, "无法读取视频任务");
  }
}

function handleContentNavigation(event, rawUrl) {
  const target = classifyNavigation(rawUrl);
  if (target.action === "allow") return;
  event.preventDefault();
  if (target.action === "official") {
    void authenticate(target.mode);
  } else if (target.action === "external") {
    void shell.openExternal(target.url);
  }
}

function configureContentView() {
  contentView = new BrowserView({
    webPreferences: {
      partition: SHORT_DRAMA_PARTITION,
      preload: path.join(__dirname, "content-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  mainWindow.setBrowserView(contentView);
  resizeContentView();
  contentView.webContents.on("will-navigate", handleContentNavigation);
  contentView.webContents.on("will-redirect", handleContentNavigation);
  contentView.webContents.on("did-navigate", (_event, url) => publishState({ contentUrl: url }));
  contentView.webContents.on("did-navigate-in-page", (_event, url) => publishState({ contentUrl: url }));
  contentView.webContents.on("did-start-loading", () => publishState({ loading: true, message: "正在加载短剧工作台…" }));
  contentView.webContents.on("did-stop-loading", () => publishState({ loading: false }));
  contentView.webContents.on("did-fail-load", (_event, code, description, url, isMainFrame) => {
    if (!isMainFrame || code === -3) return;
    publishState({ loading: false, message: `短剧工作台连接失败：${description}` , contentUrl: url });
  });
  contentView.webContents.setWindowOpenHandler(({ url }) => {
    const target = classifyNavigation(url);
    if (target.action === "official") void openOfficialPage(target.url.includes("pricing") ? "subscription" : "account");
    else if (target.action === "external") void shell.openExternal(target.url);
    return { action: "deny" };
  });
  void contentView.webContents.loadURL(`${SHORT_DRAMA_ORIGIN}/`);
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 960,
    minWidth: 1100,
    minHeight: 720,
    show: false,
    title: "古龙短剧",
    icon: path.join(__dirname, "../assets/icon.png"),
    autoHideMenuBar: true,
    backgroundColor: "#f3f4f6",
    webPreferences: {
      preload: path.join(__dirname, "shell-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  Menu.setApplicationMenu(null);
  mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  configureContentView();
  mainWindow.on("resize", resizeContentView);
  mainWindow.on("maximize", resizeContentView);
  mainWindow.on("unmaximize", resizeContentView);
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("closed", () => {
    if (contentView && !contentView.webContents.isDestroyed()) contentView.webContents.close();
    contentView = null;
    mainWindow = null;
  });
  void readOfficialAccount().catch(() => publishState({ loading: false, message: "请登录古龙账号后继续" }));
}

ipcMain.handle("desktop:get-state", () => desktopState);
ipcMain.handle("desktop:authenticate", (_event, mode) => authenticate(mode));
ipcMain.handle("desktop:open-official-page", async (_event, page) => {
  try { return await openOfficialPage(page); } catch (error) { return serializeError(error); }
});
ipcMain.handle("desktop:create-video-task", (_event, input) => createVideoTask(input));
ipcMain.handle("desktop:list-video-tasks", () => listVideoTasks());
ipcMain.handle("desktop:refresh-account", async () => {
  try {
    const account = await readOfficialAccount();
    return account ? { ok: true, account } : { ok: false, code: "AUTH_REQUIRED", message: "请先登录古龙账号" };
  } catch (error) { return serializeError(error); }
});
ipcMain.handle("desktop:navigate", (_event, action) => {
  if (!contentView || contentView.webContents.isDestroyed()) return { ok: false };
  if (action === "back" && contentView.webContents.canGoBack()) contentView.webContents.goBack();
  else if (action === "forward" && contentView.webContents.canGoForward()) contentView.webContents.goForward();
  else if (action === "reload") contentView.webContents.reload();
  else if (action === "home") void contentView.webContents.loadURL(`${SHORT_DRAMA_ORIGIN}/`);
  return { ok: true };
});

app.whenReady().then(() => {
  app.setAppUserModelId("com.sologle.shortdrama");
  createMainWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createMainWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("will-quit", () => {
  if (officialServiceWindow && !officialServiceWindow.isDestroyed()) officialServiceWindow.destroy();
});
