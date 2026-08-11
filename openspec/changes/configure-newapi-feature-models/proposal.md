## Why

当前项目同时存在官方网关、自定义 NewAPI、环境变量和多个云 Provider 直连链路，模型来源与功能选择分散，用户无法在一个配置页中完成“连接网关、同步模型、绑定功能”的完整操作。需要将云模型来源收敛为用户自定义的 NewAPI，并通过显式功能映射避免模型误选、隐藏回退和历史默认值继续生效。

## What Changes

- 配置页只保留一套自定义 NewAPI 地址与 API Key，支持连接测试、模型同步、同步状态和错误展示。
- 从 NewAPI 的 `/models` 接口同步完整模型列表，保留原始元数据、可用状态、自动推断类型和用户手动类型。
- 建立文本、视觉文本、生图、视频、音频和 Embedding 等功能槽位，每个槽位显式绑定一个模型或保持未配置。
- 模型类型仅用于推荐和筛选；无法识别的模型不自动选中，但始终可以通过“全部模型”下拉列表手动选择。
- 运行时统一按功能 ID 读取全局功能绑定；所有项目使用同一绑定，请求和项目配置不得覆盖模型。没有绑定时明确报错，不再静默使用产品默认模型。
- 将原“官方渠道”改为指向 `https://newapi.chonghuayunke.com` 的外部超链接，文案为“没有可用的 NewAPI 服务？获取官方服务”，不再参与鉴权、模型映射或运行时路由。
- **BREAKING** 云端模型调用不再使用官方模式或 Provider 直连配置；历史项目中的图片 selection、视频 backend 等字段需要迁移或兼容读取。

## Capabilities

### New Capabilities

- `custom-newapi-connection`: 保存、规范化、脱敏展示并测试唯一的自定义 NewAPI 连接，同时提供官方服务外链。
- `newapi-model-catalog`: 从 NewAPI 同步模型目录，跟踪模型可用性，并支持自动推断和手动指定模型类型。
- `feature-model-binding`: 按业务功能绑定模型，提供按类型推荐和“全部模型”选择，并校验必需功能是否已配置。
- `feature-model-runtime-routing`: 运行时只通过功能 ID 解析和调用全局绑定的 NewAPI 模型，并禁止请求或项目级模型覆盖。

### Modified Capabilities

<!-- 当前 OpenSpec 主规格目录为空，本变更不修改既有 capability。 -->

## Impact

- 后端：`model_gateway_settings.py`、`config.py`、`model_gateway_runtime.py`、`api/routes/model_gateway.py`，以及文本、图片、视频、音频、Embedding 的生成器和任务 Runner。
- 前端：模型网关查询、设置对话框、功能模型清单及相关 Zustand 编辑状态。
- 数据：`settings.db` 增加连接、同步模型目录、功能绑定和配置版本；历史 `project_config.json` 增加迁移逻辑。
- API：新增或调整连接测试、模型同步、模型分类、功能绑定和功能测试接口。
- 运维：官方服务 URL 变为普通可配置外链；云端 Provider 密钥和直连分支逐步退出运行链路。
