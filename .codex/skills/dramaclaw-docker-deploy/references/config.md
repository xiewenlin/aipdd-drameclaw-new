# DramaClaw CE Deployment Configuration

Only the values in the Fixed values section are stored in this Skill. All other deployment settings must be supplied at runtime or discovered from the current repository. Ask for missing values before deployment.

## Fixed values

- Docker Hub organization: claymorelab
- Backend image repository: claymorelab/dramaclaw
- Frontend image repository: claymorelab/dramaclaw-frontend
- Default version tag: latest (use DRAMACLAW_VERSION env var to pin)
- Backend internal port: 8780
- Frontend internal port: 80
- Default API host port: 8780
- Default Web host port: 8080
- Default NewAPI host port: 3000- Official model service URL: https://newapi.chonghuayunke.com
- Default PostgreSQL host port: 5432
- NewAPI image: calciumion/new-api:v1.0.0-rc.21
- PostgreSQL image: postgres:16-alpine
- Database name: dramaclaw
- Database user: dramaclaw
- Data volume: ce-data
- Database volume: db-data
- NewAPI volume: newapi-data
- Default timezone: Asia/Shanghai
- Python version: 3.12 (slim base)
- Node version: 22 (alpine)

## Compose file matrix

| Compose file | Source | NewAPI mode | Services |
|---|---|---|---|
| docker-compose.yml | Local build | Official DC key provisioner | db + api + web |
| docker-compose.release.yml | Docker Hub release | Official DC key provisioner | api + web |
| docker-compose.selfhosted.yml | Local build | Self-hosted new-api (SQLite) | api + newapi + web |
| docker-compose.selfhosted.release.yml | Docker Hub release | Self-hosted new-api (SQLite) | api + newapi + web |

## Runtime inputs required before production deployment

- Server host or SSH alias
- SSH user and authentication method (SSH key preferred)
- Remote deployment directory
- Deployment mode (official-gateway vs self-hosted new-api)
- Image source (local build vs Docker Hub release)
- Domain name (if behind reverse proxy)
- Database password (if not using default)
- DB encryption key (must be at least 32 chars for production)
- Model gateway API key or New API upstream credentials
- Media relay provider credentials (if using OSS relay for reference images)

Never save these runtime inputs in this Skill. Never print or commit secrets.

## Required production environment baseline

The deployment must set these before starting in production:

~~~env
DB_PASSWORD=<strong-password>
DB_ENCRYPTION_KEY=<at-least-32-chars-secret>
ST_COOKIE_SECURE=1
RELEASE_NOTIFICATIONS_ENABLED=true
~~~

Optional production environment:

~~~env
ST_API_PORT=8780
ST_WEB_PORT=8080
ST_NEWAPI_PORT=3000
DRAMACLAW_VERSION=latest
INSTALL_WORLD=0
NEWAPI_BASE_URL=<external-gateway-url>
NEWAPI_API_KEY=<gateway-token>
MEDIA_RELAY_PROVIDER=aliyun_oss
OSS_RELAY_ENDPOINT=oss-cn-chengdu.aliyuncs.com
OSS_RELAY_BUCKET=claymore-llm-relay
OSS_RELAY_AK=<access-key>
OSS_RELAY_SK=<secret-key>
PROMPT_EXPORT_PASSWORD=<change-me>
~~~

## Health check endpoints

- Backend: GET http://127.0.0.1:8780/api/v1/config (container built-in healthcheck)
- Backend: GET http://127.0.0.1:8780/api/health (if available)
- NewAPI: GET http://127.0.0.1:3000/api/status
- Frontend: GET http://127.0.0.1:8080/ (should return HTML with assets/index-*.js)

## Reverse proxy contract (Nginx)

For Nginx on the host, proxy these routes to the web service (127.0.0.1:8080):

- /
- /api/
- /static/

For Nginx inside the Docker network, use the Compose service name `web:80` or `api:8780` directly.
