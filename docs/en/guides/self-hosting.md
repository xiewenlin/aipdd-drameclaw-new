<!-- lang-switch -->
**English** · [简体中文](../../zh/guides/self-hosting.md)

# Self-Hosting Handbook (Docker)

DramaClaw CE runs `api` and `web` by default. All cloud models connect through one configured NewAPI service.

## Start

```bash
git clone https://github.com/dramaclaw/dramaclaw.git
cd dramaclaw
cp .env.example .env
docker compose up -d --build
```

Use at least 2 vCPU / 4 GB RAM and replace password-like defaults in `.env` before deployment.

## Configure Models

1. Open `http://localhost:8080` -> Settings -> Model Configuration.
2. Enter one NewAPI URL and API key, then test it.
3. Synchronize `/models`.
4. Bind a model to each feature. Unclassified models are not auto-selected but remain in the all-models list.

Every project shares this configuration; project and request overrides are unsupported. The official entry is only an external [NewAPI service link](https://newapi.chonghuayunke.com). Enter the resulting URL and key through the same flow.

To run the bundled NewAPI container:

```bash
docker compose -f docker-compose.selfhosted.yml up -d --build
```

Manage upstream channels and mappings in NewAPI itself, then enter its reachable URL and runtime token in Model Configuration. DramaClaw no longer configures direct cloud-provider channels.

## Operations and Troubleshooting

```bash
docker compose ps
docker compose logs -f api
docker compose down
git pull
docker compose up -d --build
```

| Symptom | Check |
|---|---|
| Containers do not start | Inspect `docker compose logs api`. |
| Model sync fails | Check the global NewAPI URL, key, and `/models`. |
| A feature call fails | Verify its binding and run the feature test. |
| Cognee uses old settings | Restart the API when prompted. |

## Related

- [Configuring Models](../getting-started/configuring-models.md)
- [Environment Variables](../reference/environment-variables.md)