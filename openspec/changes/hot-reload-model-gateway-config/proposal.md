## Why

CE 设置页保存 NewAPI 地址、Key 或知识库模型后，普通模型调用可以读取新配置，但 Cognee 仍持有进程启动时的全局 LLM/Embedding 配置，导致用户必须重启后端才能继续知识库任务。生产环境需要让新配置自动生效，同时保证执行中的任务不会在中途混用两代模型配置。

## What Changes

- 增加进程内模型运行时协调器，以 `runtimeRevision` 和有效配置指纹检测连接、知识库 LLM、Embedding 模型及维度变化。
- Cognee 任务在完整操作期间持有配置代际租约；已有任务使用旧快照执行完毕，新任务在旧代排空后使用最新配置。
- 将 Cognee 的环境变量、`cognee.config`、LLM/Embedding 客户端缓存和补丁状态作为一次原子重配置处理；失败时禁止新任务静默使用旧配置。
- 多次连续保存配置时合并到最新版本，不为中间版本重复初始化；多进程部署中的每个工作进程在任务入口自行检测并收敛。
- 设置页状态由“需要重启 Cognee”改为“待应用、排空中、应用中、已生效或应用失败”，并展示期望版本和当前版本。
- 当 Embedding 模型或向量维度变化时，服务本身无需重启，但已有知识库必须明确提示重建，禁止混用不兼容向量。
- 保持当前全局配置规则，不增加项目级或请求级模型覆盖。

## Capabilities

### New Capabilities

- `model-runtime-hot-reload`: 定义全局模型配置的版本检测、任务级一致性、Cognee 原子热重载、运行状态和 Embedding 兼容性保护。

### Modified Capabilities

<!-- 当前 openspec/specs 目录没有已归档的主规格；本变更作为独立能力补充现有 NewAPI 方案。 -->

## Impact

- 后端：`model_gateway_runtime.py`、`model_catalog.py`、`cognee/config.py`、`cognee/store.py` 和模型网关 API。
- 前端：设置页模型网关状态、保存反馈和知识库重建提示。
- 数据：沿用 `settings.db` 的 `runtimeRevision`，并为项目知识库记录 Embedding 模型与维度签名。
- 并发：Cognee 配置切换期间，新知识库任务可能短暂等待当前旧代任务完成；普通文本、图片、视频和音频任务不被阻塞。
- 部署：不新增外部服务或强制依赖；单进程和多进程工作进程均通过共享配置版本惰性收敛。
