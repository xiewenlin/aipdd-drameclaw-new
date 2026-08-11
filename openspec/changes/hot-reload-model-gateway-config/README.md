# hot-reload-model-gateway-config

Apply NewAPI connection and feature-model changes to Cognee without restarting the backend.
## Validation record

- Focused backend suite: 99 passed.
- Frontend: `npm run build` passed (`tsc -b` and Vite production build).
- OpenSpec: `openspec validate hot-reload-model-gateway-config --strict` passed.
- Secret scan: the workspace is not a Git repository, no `gitleaks` binary is installed, and the execution environment blocked downloading the official temporary binary. No secret-scan result is claimed; run `gitleaks dir . --redact` in CI or a release workspace with Gitleaks installed.
