<!-- lang-switch -->
**English** · [简体中文](../../zh/reference/environment-variables.md)

# Environment Variables

> Create `.env` from `.env.example`. Model URLs, API keys, and feature-model bindings are not configured through environment variables.

## Model Runtime

The only cloud-model entry point is Settings -> Model Configuration. Global `settings.db` stores one NewAPI URL and key, the `/models` catalog, and feature bindings for text, vision, image, video, audio, and embedding.

`MODEL_NAME`, other `*_MODEL` variables, provider keys, separate base URLs, and project/request model fields are legacy settings and do not select runtime models. Transport-only settings such as `NEWAPI_TEXT_TIMEOUT_SECONDS` and `NEWAPI_TEXT_TRUST_ENV` remain configurable through the environment.

## Common Variables

| Variable | Default | Description |
|---|---|---|
| `ST_EDITION` | `ce` | Edition identifier. |
| `NOVELVIDEO_DATA_ROOT` | `.` (`/data` in Docker) | Data root. |
| `NOVELVIDEO_OUTPUT_DIR` | `$DATA_ROOT/output` | Output directory. |
| `NOVELVIDEO_STATE_DIR` | `$DATA_ROOT/state` | State directory containing `settings.db`. |
| `NEWAPI_TEXT_TIMEOUT_SECONDS` | `120` | Text request timeout. |
| `NEWAPI_TEXT_TRUST_ENV` | `true` | Whether clients read system proxy settings. |
| `EMBEDDING_BATCH_SIZE` | `10` | Embedding batch size; does not select a model. |
| `VIDEO_FPS` | `30` | Output frame rate. |
| `VIDEO_WIDTH` / `VIDEO_HEIGHT` | `1080` / `1920` | Output dimensions. |
| `FFMPEG_PATH` | `ffmpeg` | ffmpeg path. |
| `PROMPT_EXPORT_PASSWORD` | `change_me` | Must be overridden in deployments. |

OSS/Cloudinary variables configure reference-media relay only. Explicit local transports such as ComfyUI may retain their own connection settings.

## Related

- [Configuring Models](../getting-started/configuring-models.md)
- [Self-Hosting Handbook](../guides/self-hosting.md)