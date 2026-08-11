---
name: dramaclaw-docker-deploy
description: "Deploy, upgrade, roll back, and verify DramaClaw CE (SuperTale Community Edition) Docker Compose deployments from the current workspace. Use when a user asks to deploy or update DramaClaw, build or publish Docker images, set up a new self-hosted instance, configure the model gateway (official DC key or new-api), back up or restore PostgreSQL data, or troubleshoot Docker Compose, Nginx, PostgreSQL, or new-api configuration."
---

# DramaClaw CE Docker Deploy

Use this skill to operate DramaClaw CE Docker Compose deployments from the current workspace. Read references/config.md before executing commands; it contains fixed image repositories, ports, and the compose file matrix. All deployment-specific inputs must be supplied at runtime or discovered from the current repository.

## Operating rules

- Treat the current workspace as the source of truth for application code and Compose configuration.
- Preserve unrelated user changes. Never run reset, checkout, clean, force-push, or destructive file operations to make the workspace clean.
- Never write, print, commit, or put into a command line any API key, database password, encryption key, OSS secret, or other secret. Use environment variables or interactive credential prompts.
- During execution, never print credentials. Never return or regenerate the DB_ENCRYPTION_KEY during an update.
- Never execute `docker compose down -v`, `docker system prune`, or destructive database changes without explicit user approval in the current request.
- Before replacing a production container with new images, back up the PostgreSQL database and report the backup path.
- Do not commit or push Git changes unless the user explicitly asks for Git commit or push. Deployment and Git publication are separate actions.
- Do not assume or persist a server IP, SSH user, SSH password, deployment directory, domain name, or any credentials.
- The release images on Docker Hub (claymorelab/dramaclaw, claymorelab/dramaclaw-frontend) are CE "slim" images without 3DGS/SHARP/world features. World features require a local source build with `INSTALL_WORLD=1`.

## Decide the operation

1. Inspect the current repository, Git status, Compose files, Dockerfile, and environment files.
2. Classify the request:
   - **Local dev start**: start the stack locally for development, using local build or release images.
   - **First deployment / initialization**: set up a new server with Docker Compose, configure secrets, create initial admin.
   - **Update / upgrade**: pull new images or rebuild, recreate application services, preserve data.
   - **Image build & publish**: build and push backend/frontend images to a registry.
   - **Server-only update**: pull existing image tag on a remote server, back up database, recreate app service.
   - **Rollback**: use the explicitly named previous image tag or digest; never guess a rollback version.
   - **Configuration repair**: fix the local configuration first, rebuild or restart, then verify.
   - **Gateway mode change**: switch between official DC key provisioner and self-hosted new-api.
3. Select the correct Compose file based on mode:
   - Official gateway + local build: `docker-compose.yml`
   - Official gateway + release images: `docker-compose.release.yml`
   - Self-hosted new-api + local build: `docker-compose.selfhosted.yml`
   - Self-hosted new-api + release images: `docker-compose.selfhosted.release.yml`
4. Before any remote operation, collect these runtime inputs. Ask for each missing item and stop until the user answers:
   - Server host or SSH alias
   - SSH user and SSH key or interactive authentication method
   - Remote deployment directory
   - Deployment mode (official-gateway vs self-hosted new-api)
   - Image source preference (local build vs Docker Hub release)
   - Domain name (if behind reverse proxy; default: none, direct port access)
   - Database password (if production)
   - DB encryption key (at least 32 chars for production)
   - Model gateway API key or New API upstream credentials

## Deployment modes

### Mode 1: Official DC key provisioner (simplest)

Uses the official model gateway. Users paste their DC key in the web UI after first launch. No separate new-api container needed.

Compose files: `docker-compose.yml` (local build) or `docker-compose.release.yml` (release images).

Services: PostgreSQL (db) + API + Web (nginx frontend)

### Mode 2: Self-hosted new-api (full control)

Runs an internal new-api gateway container. Users configure upstream channels and tokens in new-api admin UI. More setup, full control.

Compose files: `docker-compose.selfhosted.yml` (local build) or `docker-compose.selfhosted.release.yml` (release images).

Services: API + new-api + Web (nginx frontend)

Note: release images in self-hosted mode have `NEWAPI_PROVISIONER_ENABLED=false` by default. Users manually configure new-api at port 3000 then set `NEWAPI_API_KEY`.

## Local development deployment

Use for local testing and development on the current machine.

### Quick start (official gateway, release images)

~~~bash
docker compose -f docker-compose.release.yml up -d
# Open http://localhost:8080
# Go to Settings -> Model config -> Official channel -> Paste DC key
~~~

### Quick start (self-hosted new-api, release images)

~~~bash
docker compose -f docker-compose.selfhosted.release.yml up -d
# Open http://localhost:3000 to set up new-api admin and channels
# Then set NEWAPI_API_KEY in .env and restart api
~~~

### Local source build (official gateway)

~~~bash
docker compose up --build -d
~~~

### Local source build with world features (3DGS/SHARP)

~~~bash
INSTALL_WORLD=1 docker compose up --build -d
~~~

### Stop the stack (preserves data)

~~~bash
docker compose down
~~~

## Image building and publishing

Build the backend image:

~~~bash
docker build -t dramaclaw:dev .
# With world features:
docker build --build-arg INSTALL_WORLD=1 -t dramaclaw:world .
~~~

Build the frontend image:

~~~bash
cd frontend
docker build --build-arg VITE_APP_VERSION=dev -t dramaclaw-frontend:dev .
~~~

To publish to a registry, tag and push:

~~~bash
# Backend
docker tag dramaclaw:dev your-registry/dramaclaw:latest
docker push your-registry/dramaclaw:latest

# Frontend
docker tag dramaclaw-frontend:dev your-registry/dramaclaw-frontend:latest
docker push your-registry/dramaclaw-frontend:latest
~~~

If the registry requires authentication, use `docker login` interactively or an already configured credential helper. Never place the password in the command, shell history, or skill files.

## Initial deployment (first install on remote server)

Use initialization only when the user explicitly requests a first deployment, new installation, or fresh instance.

Before initialization, ask for any missing runtime values listed in "Decide the operation" section.

Initialization rules:

1. Check whether the remote directory, Compose containers, or volumes already exist. If existing data is found, stop and ask whether this is a re-initialization; never overwrite it automatically.
2. Ensure Docker and Docker Compose are installed on the target server.
3. Create the deployment directory and `.env` file with all required production values.
4. Enforce strong production values:
   - `DB_PASSWORD` must be a strong random password (minimum 24 chars)
   - `DB_ENCRYPTION_KEY` must be at least 32 chars of cryptographically secure randomness
   - `ST_COOKIE_SECURE=1` when HTTPS is configured
   - `PROMPT_EXPORT_PASSWORD` must be set to a non-default value
5. Deploy the selected Compose stack and wait for all services to become healthy.
6. Verify the deployment (see "Verify deployment" section below).
7. For self-hosted mode, guide the user to set up new-api admin at port 3000, configure channels and tokens, then set `NEWAPI_API_KEY` and restart the api service.
8. Return the generated credentials (DB password, encryption key, export password) exactly once in the final report because the user explicitly requested initialization. Never return them during an update.

### Initial deployment steps

On the remote server:

~~~bash
mkdir -p /opt/dramaclaw
cd /opt/dramaclaw
mkdir -p backups
~~~

Copy the selected Compose file and create `.env` with production values. Then:

~~~bash
cd /opt/dramaclaw
docker compose -f <compose-file> up -d
~~~

Wait for health checks to pass, then verify.

## Update deployment

Use for updating an existing deployment. Preserves all data, volumes, .env, and configuration.

### Update steps (release images, official gateway)

~~~bash
cd <deployment-directory>
mkdir -p backups

# Backup PostgreSQL (if using db service)
docker exec dramaclaw-db-1 sh -c 'exec pg_dump -U dramaclaw dramaclaw' \
  | gzip > "backups/dramaclaw_$(date +%Y%m%d_%H%M%S).sql.gz"

# Pull new images
docker compose -f docker-compose.release.yml pull

# Recreate only changed services
docker compose -f docker-compose.release.yml up -d --no-build
~~~

### Update steps (local source build)

~~~bash
cd <deployment-directory>
mkdir -p backups

# Backup PostgreSQL
docker exec dramaclaw-db-1 sh -c 'exec pg_dump -U dramaclaw dramaclaw' \
  | gzip > "backups/dramaclaw_$(date +%Y%m%d_%H%M%S).sql.gz"

# Rebuild and recreate
docker compose up --build -d
~~~

### Update steps (self-hosted mode)

Same as above but use `docker-compose.selfhosted.yml` or `docker-compose.selfhosted.release.yml`.

Do not recreate or remove the PostgreSQL or new-api container unless the user explicitly asks. Wait for the api and web containers to become healthy. If they do not become healthy, collect the last 200 application log lines, leave the old database intact, and report the failure.

## Verify deployment

Run all applicable checks:

~~~bash
# Container status
docker compose -f <compose-file> ps

# Backend health
docker inspect <api-container> --format='IMAGE={{.Config.Image}} STATUS={{.State.Status}} HEALTH={{.State.Health.Status}} RESTARTS={{.RestartCount}}'
curl -fsS http://127.0.0.1:8780/api/v1/config

# Frontend
curl -fsS http://127.0.0.1:8080/ | grep -oE 'assets/index-[^"]+\.js'

# NewAPI (self-hosted mode only)
curl -fsS http://127.0.0.1:3000/api/status

# Recent logs
docker compose -f <compose-file> logs --tail=50 api
docker compose -f <compose-file> logs --tail=20 web
~~~

When a domain is configured, verify from outside the server:

~~~bash
curl -fsS https://<domain>/api/v1/config
curl -fsS https://<domain>/ | grep -oE 'assets/index-[^"]+\.js'
~~~

Confirm the frontend bundle does not contain internal IP addresses or stale configuration.

## Database backup and restore

### Backup

~~~bash
# For PostgreSQL (official gateway mode with db service)
docker exec <db-container> sh -c 'exec pg_dump -U dramaclaw dramaclaw' \
  | gzip > "backups/dramaclaw_$(date +%Y%m%d_%H%M%S).sql.gz"

# For new-api SQLite (self-hosted mode)
docker cp <newapi-container>:/data/one-api.db backups/new-api-$(date +%Y%m%d_%H%M%S).db
~~~

### Restore

Only restore with explicit user approval.

~~~bash
# Restore PostgreSQL
gunzip -c backups/dramaclaw_YYYYMMDD_HHMMSS.sql.gz | \
  docker exec -i <db-container> psql -U dramaclaw -d dramaclaw
~~~

## Production configuration contracts

- Database data stays in the `db-data` named volume; application data stays in `ce-data`; new-api data stays in `newapi-data`.
- A normal `docker compose down` preserves volumes. Never use `down -v` during routine deployment.
- The `web` service (nginx) reverse-proxies `/api/` and `/static/` to the `api` service on port 8780.
- For production behind Nginx: proxy all traffic to `127.0.0.1:8080` (the web service). The web service handles /api proxying internally.
- `ST_COOKIE_SECURE=1` requires HTTPS; set to 0 for HTTP-only deployments.
- `DB_ENCRYPTION_KEY` must be at least 32 characters and must never change after first use (it encrypts stored secrets like API keys in the database).
- World/3DGS features are not available in release images; they require `INSTALL_WORLD=1` local build.
- The slim image uses CPU only. GPU acceleration requires a CUDA base image and nvidia runtime.

## Failure handling

- **Image pull denied**: verify registry path, repository name, tag, and server registry credentials.
- **App unhealthy**: inspect Compose status, application logs, healthcheck output, port 8780, database health, and env loading.
- **Database connection error**: check `DATABASE_URL`, `DB_PASSWORD`, PostgreSQL container status, and network connectivity between services.
- **Old frontend still visible**: inspect the HTML entry filename, container image ID, and browser cache. Do not assume a successful container recreate changed the public route.
- **Model gateway not working**: check `NEWAPI_BASE_URL`, `NEWAPI_API_KEY`, new-api container health (self-hosted), or provisioner settings (official mode).
- **Missing assets (login bgm/video)**: verify the Docker build included assets from `src/novelvideo/assets/`. The Dockerfile has asset integrity checks.
- **World features not available**: confirm `INSTALL_WORLD=1` was set during build. Release images do not include world features.

## Completion report

Report:

1. Deployment mode (official gateway / self-hosted new-api) and image source (local build / release).
2. Image tags and versions deployed.
3. Container health status and restart counts for all services.
4. Database backup path (if backup was performed).
5. Local and external health-check results.
6. Frontend entry bundle verification.
7. For initialization, the newly generated credentials (DB password, encryption key, export password) exactly once; for updates, explicitly state that all credentials and data were preserved.
8. Any skipped action, failed action, or required user input.
