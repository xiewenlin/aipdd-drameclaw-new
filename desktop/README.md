# 古龙短剧 Windows 桌面版

桌面端采用“线上 Vercel 全栈站 + Electron 安全桌面壳”架构。短剧功能继续由线上站点更新，Windows 客户端负责原生窗口、统一账号跳转、会员/充值入口和古龙官网视频任务网关，因此网页功能升级后无需重新开发整套桌面 UI。

## 用户链路

- 登录、注册：显示古龙官网的 `AccountModal`，成功后通过一次性 SSO assertion 换取短剧站 HttpOnly 会话。
- 订阅：打开古龙官网 `/pricing`，沿用官网订单、微信支付与会员状态。
- 充值：打开古龙官网 `/pricing#recharge`，沿用官网余额与支付记录。
- 视频任务：桌面壳调用 `POST https://sologle.com/api/h3/tasks`，固定 `source_channel=desktop_agent` 与 `model=minimax_h3_shared`；官网负责鉴权、整数分核价、余额预扣、幂等和任务排队。
- 任务列表：桌面壳调用 `GET https://sologle.com/api/h3/tasks`。

桌面端不保存古龙账号密码、支付密钥或 SSO assertion。官网会话与短剧站会话分别存放在 Electron 的持久化隔离分区中。

## 本地运行和构建

```powershell
cd desktop
npm install
npm test
npm run start
npm run build:win
```

Windows 安装包与免安装版输出到 `desktop/release/`。
