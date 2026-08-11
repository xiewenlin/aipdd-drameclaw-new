<!-- lang-switch -->
[English](../../en/getting-started/configuring-models.md) · **简体中文**

# 配置模型

DramaClaw 只使用一个全局 NewAPI 连接。文本、视觉、生图、视频、音频和 Embedding 都通过设置页的功能绑定选择模型；项目和单次请求不能覆盖模型、地址或凭证。

## 配置步骤

1. 打开 `http://localhost:8080`，进入“设置 → 模型配置”。
2. 填写 NewAPI 地址和 API Key，保存后点击“测试连接”。地址可以带或不带 `/v1`，系统会统一规范化。
3. 点击“同步模型”，系统从 `{baseUrl}/models` 获取模型目录。
4. 为每个功能选择模型并保存。下拉优先展示能力匹配的推荐模型，也可切换到全部模型。
5. 无法判断用途的模型标记为 `unknown` 且不会自动绑定；仍可从全部模型中手动选择，或先编辑模型能力。
6. 使用功能测试确认文本、图片、视频、音频和 Embedding 协议是否兼容。

配置保存在全局 `settings.db`，所有项目共享。保存 NewAPI 地址、Key、知识库 LLM 或 Embedding 后无需重启后端：正在执行的知识库任务继续使用原配置完成，新任务等待旧任务结束后自动使用最新配置。连续保存多次时只应用最后一份配置。

运行时状态包括 `pending`、`draining`、`applying`、`ready` 和 `failed`。新任务等待热更新的默认上限是 120 秒，可通过 `MODEL_RUNTIME_RELOAD_WAIT_TIMEOUT` 调整。应用失败时系统会阻止新知识库任务继续使用旧凭证，并在设置页显示已脱敏错误；修正配置并重新保存即可重试。

Embedding 签名由模型 ID、向量维度和向量语义参数组成，不包含 NewAPI 地址或 Key。仅更换地址或 Key 不需要重建；更换 Embedding 模型、维度或相关语义参数后，已有知识库必须显式完整重建。旧项目无法可靠确认签名时也会要求重建，并返回 `knowledge_embedding_rebuild_required`。

> 临时测试配置：CE 知识库 LLM 固定直连火山方舟 `ark-code-latest`，Embedding 固定直连 `doubao-embedding-vision`（2048 维），二者均使用 `https://ark.cn-beijing.volces.com/api/coding/v3` 并共用 `ARK_API_KEY`。密钥不会写入项目配置或接口响应。NewAPI 接入完成后应移除此临时直连适配。

## 功能绑定

后端统一提供功能目录，包括文本与视觉、图片、视频、音频和 Embedding。模型能力推断只用于推荐，不限制手动选择；跨类型绑定可能在实际调用时失败。

## 不支持的覆盖

以下旧配置不再参与运行时选模：

- `.env` 中的 `MODEL_NAME`、各类 `*_MODEL`、Provider Key 或独立 Base URL。
- 项目配置中的模型、NewAPI 地址或 API Key。
- API 请求 payload、CLI 参数中的模型、Provider、地址或凭证。

旧字段只用于迁移报告。唯一云模型来源是“全局 NewAPI 连接 + 功能绑定”。ComfyUI 等明确的本地 Transport 可继续独立配置，但不能恢复云 Provider 直连。

## 官方服务

设置页中的“没有可用的 NewAPI 服务？获取官方服务”只是普通外链，不会切换运行时渠道、注入密钥或提供默认模型映射：

- <https://newapi.chonghuayunke.com>

获取服务后，仍需把 NewAPI 地址和 API Key 填入同一配置区，并同步、绑定模型。

## 排错

| 现象 | 处理 |
|---|---|
| `/models` 同步失败 | 检查地址、Key、网络和 NewAPI 模型列表接口。 |
| 模型显示 `unknown` | 编辑能力，或从“全部模型”中手动绑定。 |
| 功能提示未配置 | 为该功能保存一个全局模型绑定。 |
| 模型调用协议错误 | 使用功能测试确认对应协议兼容性。 |
| 配置保存后处于 `draining` | 等待当前知识库任务完成，系统会自动切换。 |
| 提示 `knowledge_embedding_rebuild_required` | 对该项目执行一次显式完整知识库重建。 |

## 相关

- [自托管手册](../guides/self-hosting.md)
- [环境变量参考](../reference/environment-variables.md)
## 模型配置热更新上线与回滚

热更新默认开启。建议先更新一个 worker，保存一次仅地址或 Key 变化的测试配置，等待 `runtimeState=ready` 并执行一次知识库检索，再更新其余 worker。每个 worker 会在下一次知识库操作时独立收敛到最新配置。

紧急回滚时，设置 `MODEL_RUNTIME_HOT_RELOAD_ENABLED=false` 并重启全部后端 worker。之后保存模型网关配置会把 `cognee` 加入 `restartRequiredComponents`；运行中的进程继续保留启动时配置，一旦检测到新版本就拒绝新的知识库操作，直到再次重启。恢复为 `true` 并重启 worker 后重新启用热更新。该开关不能绕过 Embedding 重建要求。

Embedding 签名变化后，需要在每个受影响项目中执行显式“完整知识库重建/重新导入”，不能使用增量导入。只有向量替换成功后才写入新签名；失败会保留旧签名，可以安全重试。
