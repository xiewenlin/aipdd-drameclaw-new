<!-- lang-switch -->
**English** · [简体中文](../../zh/getting-started/configuring-models.md)

# Configuring Models

DramaClaw uses one global NewAPI connection. Text, vision, image, video, audio, and embedding models are selected through feature bindings in Settings. Projects and individual requests cannot override the model, gateway URL, or credentials.

## Setup

1. Open `http://localhost:8080` and go to Settings -> Model Configuration.
2. Enter the NewAPI URL and API key, save, then test the connection. URLs with or without `/v1` are normalized.
3. Select Sync Models. DramaClaw loads the catalog from `{baseUrl}/models`.
4. Select and save one model for each required feature. Each selector shows recommended matches and an all-models list.
5. Models whose purpose cannot be inferred are marked `unknown` and are never auto-selected. You may select them manually or edit their capabilities.
6. Run feature tests to verify text, image, video, audio, and embedding protocol compatibility.

Configuration is stored globally in `settings.db` and shared by every project. Saving the NewAPI URL, key, knowledge LLM, or embedding binding does not require a backend restart. Active knowledge operations finish on their original configuration; new operations wait for them to drain and then use the latest saved configuration. Repeated saves are coalesced to the newest snapshot.

Runtime states are `pending`, `draining`, `applying`, `ready`, and `failed`. The default wait limit is 120 seconds and can be changed with `MODEL_RUNTIME_RELOAD_WAIT_TIMEOUT`. A failed apply blocks new knowledge operations from falling back to old credentials and exposes only a sanitized error in Settings. Save a corrected configuration to retry.

The embedding signature includes model ID, vector dimension, and vector-semantic parameters, but excludes the NewAPI URL and key. Credential-only changes do not require a rebuild. Changing the embedding model, dimension, or semantic parameters requires an explicit full knowledge-base rebuild. Legacy projects without a reliably compatible signature also return `knowledge_embedding_rebuild_required` until rebuilt.
## Rollout and Rollback

Hot reload is enabled by default. Roll it out by updating one worker first, saving a credential-only test change, waiting for `runtimeState=ready`, running a knowledge search, and then updating the remaining workers. Each worker independently converges on its next knowledge operation.

For emergency rollback, set `MODEL_RUNTIME_HOT_RELOAD_ENABLED=false` and restart every backend worker. Subsequent model-gateway saves add `cognee` to `restartRequiredComponents`; the running process keeps its startup generation and rejects knowledge operations after a changed runtime revision until restarted. Restore the variable to `true` and restart workers to re-enable hot reload. Never use this switch to bypass an Embedding rebuild requirement.

To rebuild after an Embedding signature change, open each affected project and run its explicit full knowledge-base rebuild/import action. Do not use incremental ingestion. The new signature is persisted only after vector replacement succeeds; a failed rebuild retains the previous signature and can be retried safely.

## No Per-Project Overrides

These legacy settings no longer participate in runtime model selection:

- `MODEL_NAME`, other `*_MODEL` variables, provider keys, or separate base URLs in `.env`.
- Models, NewAPI URLs, or API keys stored in project configuration.
- Model, provider, URL, or credential fields in API payloads and CLI arguments.

Legacy fields are migration-report inputs only. The sole cloud runtime source is the global NewAPI connection plus feature bindings. Explicit local transports such as ComfyUI remain available, but cannot restore direct cloud-provider routing.

## Official Service Link

The “Need a NewAPI service? Get the official service” entry is an ordinary external link. It does not select a runtime channel, inject credentials, or provide mappings:

- <https://newapi.chonghuayunke.com>

After obtaining service, enter its NewAPI URL and API key in the same settings area, then sync and bind models.

## Troubleshooting

| Symptom | Action |
|---|---|
| `/models` sync fails | Check the URL, key, network, and model-list endpoint. |
| A model is `unknown` | Edit its capabilities or select it from all models. |
| A feature is unconfigured | Save a global binding for that feature. |
| A protocol call fails | Use the feature test to verify compatibility. |
| Settings remains in `draining` | Wait for the active knowledge operation; the runtime switches automatically. |
| `knowledge_embedding_rebuild_required` | Run an explicit full knowledge-base rebuild for that project. |

## Related

- [Self-Hosting Handbook](../guides/self-hosting.md)
- [Environment Variables](../reference/environment-variables.md)