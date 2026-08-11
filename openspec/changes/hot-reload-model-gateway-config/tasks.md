## 1. Runtime Snapshot and Coordinator

- [x] 1.1 Add immutable `ModelRuntimeSnapshot` construction from persisted NewAPI connection, knowledge LLM, Embedding model, dimension, semantic parameters, and `runtimeRevision`, with a credential-safe effective fingerprint.
- [x] 1.2 Implement a process-local async runtime coordinator with `uninitialized`, `ready`, `draining`, `applying`, and `failed` states plus desired/active revisions and lease counts.
- [x] 1.3 Detect revisions at public Cognee operation boundaries, skip draining for unchanged Cognee fingerprints, and coalesce repeated saves to the newest desired snapshot.
- [x] 1.4 Add coordinator tests for unchanged fingerprints, unrelated image/video/audio bindings, repeated saves, and desired-revision coalescing.
- [x] 1.5 Add a two-worker integration test proving independent lazy convergence through the shared persisted runtime revision.

## 2. Atomic Cognee Reconfiguration

- [x] 2.1 Refactor Cognee environment variables and `cognee.config` mutation into one idempotent snapshot application adapter.
- [x] 2.2 Add explicit reset hooks for supported Cognee and LiteLLM clients/caches, and verify compatibility against the repository's locked dependency versions.
- [x] 2.3 Make snapshot application transactional: validate first, apply under the coordinator lock, roll back process-global values where possible, and block new leases after failure.
- [x] 2.4 Ensure removing or replacing credentials never falls back to an old API key and sanitize all runtime status, logs, and errors.
- [x] 2.5 Keep compatibility patch installation idempotent and add regression tests proving repeated reloads do not duplicate monkey-patching.
- [x] 2.6 Replace the Cognee restart-required branch in `init_cognee()` with coordinator initialization while retaining a temporary feature-flag rollback path.
- [x] 2.7 Add tests for successful atomic application, failed reload isolation, rollback behavior, cache reset failure, and Cognee/LiteLLM cache reset compatibility.

## 3. Cognee Operation Leases

- [x] 3.1 Add an async generation-lease context manager that snapshots one active generation and releases its counter in cleanup on success, error, or cancellation.
- [x] 3.2 Route all public Cognee import, graph, indexing, search, and agent-retrieval Store operations through the lease boundary for their complete operation lifetime.
- [x] 3.3 Prevent new lease admission during draining or applying, and wake waiting operations only after a ready generation is fully active.
- [x] 3.4 Add configurable bounded waiting that returns `model_runtime_reload_wait_timeout` without cancelling active old-generation operations.
- [x] 3.5 Add concurrency tests for drain ordering, full-operation lease consistency, waiting admission, timeout, cancellation cleanup, and no unleased public Cognee execution.

## 4. Embedding Compatibility

- [x] 4.1 Define and persist a per-project Embedding signature from normalized model identity, effective dimension, and vector-semantic parameters, excluding URL and credentials.
- [x] 4.2 Compare signatures before knowledge queries and incremental ingestion and return `knowledge_embedding_rebuild_required` with non-sensitive old/new summaries on mismatch.
- [x] 4.3 Update explicit full rebuild to write the new signature atomically only after successful vector replacement.
- [x] 4.4 Add a safe migration for legacy projects, adopting a signature only when prior compatibility is reliable and otherwise requiring rebuild.
- [x] 4.5 Add tests for model changes with equal dimensions, dimension changes, credential-only changes, legacy migration, failed rebuild retention, and successful rebuild signature replacement.

## 5. API and Settings Page

- [x] 5.1 Extend the model gateway runtime status contract with `desiredRevision`, `activeRevision`, `runtimeState`, `activeLeaseCount`, `lastAppliedAt`, and sanitized `lastReloadError`.
- [x] 5.2 Update settings-save handling to persist and increment revisions, invalidate ordinary agent caches, notify only the local coordinator, and stop adding Cognee to `restartRequiredComponents` when hot reload is enabled.
- [x] 5.3 Update the settings page to display pending, draining, applying, ready, and failed states with the message that changes apply after current knowledge tasks finish.
- [x] 5.4 Add settings-page guidance that Embedding model or dimension changes require rebuilding existing knowledge bases, while credential-only changes do not.
- [x] 5.5 Add API contract tests for status/save behavior, secret redaction, restart compatibility fields, and knowledge rebuild errors, then run the frontend type check.

## 6. Validation and Rollout

- [x] 6.1 Run focused unit and concurrency tests for the runtime coordinator, Cognee adapter, Store leases, and Embedding signatures.
- [x] 6.2 Run model gateway API tests and a real or stubbed NewAPI smoke test covering save, drain, automatic apply, and subsequent Cognee execution without restart.
- [x] 6.3 Validate single-worker and multi-worker deployments, including a worker that misses the local save notification and converges on its next operation.
- [x] 6.4 Document the feature flag, timeout, runtime states, knowledge-base rebuild procedure, rollout order, and rollback to restart-required behavior.
- [x] 6.5 Run the repository's relevant pytest suite, frontend type check, and secret scan, and record any unrelated pre-existing failures separately.
