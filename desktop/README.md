# 古龙短剧 Windows 原生桌面版

桌面端 2.0 使用 .NET 8 + WPF 原生控件实现。工作台、新建任务、我的任务、状态栏和全部导航均为 Windows 桌面组件，不加载短剧网站，也不依赖 Electron。

## 用户链路

- 登录、注册：只在独立的 WebView2 安全账号窗口中显示古龙官网表单，账号密码不会进入客户端代码。
- 订阅、充值：只在独立的古龙安全窗口中显示官网支付流程，沿用官网订单与支付记录。
- 账号状态：原生客户端通过登录会话读取 `/api/auth/me`、订阅和余额接口。
- 视频任务：原生 `HttpClient` 调用 `POST https://sologle.com/api/h3/tasks`，固定 `source_channel=desktop_agent` 与 `model=minimax_h3_shared`；官网负责鉴权、整数分核价、余额预扣、幂等和排队。
- 任务列表：原生控件展示 `GET https://sologle.com/api/h3/tasks` 的结果。

桌面端不保存古龙账号密码、支付密钥或一次性授权。官网 Cookie 由 WebView2 存放在当前 Windows 用户的本地应用数据目录中，并同步到进程内 CookieContainer；退出进程后内存副本即销毁。

## 本地运行和构建

需要 .NET 8 SDK、WebView2 Runtime 和 NSIS。运行：

```powershell
cd desktop
.\build-native.ps1
```

Windows 安装包与单文件便携版输出到 `desktop/release/`。最终用户无需安装 .NET；Windows 10/11 通常已包含 WebView2 Runtime。
