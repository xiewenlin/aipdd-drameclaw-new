<!-- lang-switch -->
[English](../../en/reference/environment-variables.md) · **简体中文**

# 环境变量参考

> 从 `.env.example` 创建 `.env`。模型地址、API Key 和功能模型绑定不通过环境变量配置。

## 模型运行时

唯一云模型配置入口是网页“设置 → 模型配置”。全局 `settings.db` 保存一个 NewAPI 地址和 Key、从 `/models` 同步的目录，以及文本、视觉、图片、视频、音频和 Embedding 的功能绑定。

`MODEL_NAME`、各类 `*_MODEL`、Provider Key、独立 Base URL，以及项目/请求级模型字段均为旧配置，不参与运行时选择。`NEWAPI_TEXT_TIMEOUT_SECONDS`、`NEWAPI_TEXT_TRUST_ENV` 等纯传输参数仍可由环境变量调整。

## 常用变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `ST_EDITION` | `ce` | 版本标识。 |
| `NOVELVIDEO_DATA_ROOT` | `.`（Docker 为 `/data`） | 数据根目录。 |
| `NOVELVIDEO_OUTPUT_DIR` | `$DATA_ROOT/output` | 输出目录。 |
| `NOVELVIDEO_STATE_DIR` | `$DATA_ROOT/state` | 包含 `settings.db` 的状态目录。 |
| `NEWAPI_TEXT_TIMEOUT_SECONDS` | `120` | 文本请求超时。 |
| `NEWAPI_TEXT_TRUST_ENV` | `true` | 是否读取系统代理。 |
| `EMBEDDING_BATCH_SIZE` | `10` | Embedding 批大小，不选择模型。 |
| `VIDEO_FPS` | `30` | 输出帧率。 |
| `VIDEO_WIDTH` / `VIDEO_HEIGHT` | `1080` / `1920` | 输出尺寸。 |
| `FFMPEG_PATH` | `ffmpeg` | ffmpeg 路径。 |
| `PROMPT_EXPORT_PASSWORD` | `change_me` | 部署时必须覆盖。 |

OSS/Cloudinary 环境变量只用于参考媒体 relay。ComfyUI 等本地 Transport 可保留自己的连接参数。

## 相关

- [配置模型](../getting-started/configuring-models.md)
- [自托管手册](../guides/self-hosting.md)