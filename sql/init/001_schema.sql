-- =============================================================================
-- DramaClaw CE Multi-User Schema
-- 自动导入：PostgreSQL 官方镜像 /docker-entrypoint-initdb.d/
-- 首次启动时自动执行，已初始化后不会重复运行
-- =============================================================================

-- 启用 UUID 生成
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. 用户表
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(64)  NOT NULL UNIQUE,
    email           VARCHAR(255) UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(32)  NOT NULL DEFAULT 'user',
    status          VARCHAR(32)  NOT NULL DEFAULT 'active',
    display_name    VARCHAR(128),
    avatar_url      VARCHAR(512),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);

-- =============================================================================
-- 2. 用户会话表
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token   VARCHAR(64) NOT NULL UNIQUE,
    device_info     VARCHAR(256),
    ip_address      VARCHAR(64),
    user_agent      TEXT,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id  ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token    ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires  ON user_sessions(expires_at);

-- =============================================================================
-- 3. 用户模型网关配置
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_model_configs (
    user_id              UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    gateway_mode         VARCHAR(16)  NOT NULL DEFAULT 'official',
    newapi_base_url      VARCHAR(512),
    newapi_api_key       VARCHAR(512),
    media_relay_provider VARCHAR(32)  DEFAULT 'aliyun_oss',
    media_relay_ttl      INTEGER      DEFAULT 1800,
    oss_endpoint         VARCHAR(256),
    oss_bucket           VARCHAR(128),
    oss_ak               VARCHAR(128),
    oss_sk               VARCHAR(512),
    cognee_provider      VARCHAR(64),
    cognee_model         VARCHAR(128),
    cognee_dimensions    VARCHAR(16),
    embedding_batch_size VARCHAR(16),
    image_default_width  INTEGER      DEFAULT 1440,
    image_default_height INTEGER      DEFAULT 2560,
    image_default_style  VARCHAR(64)  DEFAULT 'chinese_period_drama',
    video_resolution     VARCHAR(16)  DEFAULT '720p',
    video_generate_audio VARCHAR(16)  DEFAULT 'auto',
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- 4. 用户渠道配置
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_provider_channels (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_type   INTEGER      NOT NULL,
    name            VARCHAR(128) NOT NULL,
    base_url        VARCHAR(512),
    api_key         VARCHAR(512),
    weight          INTEGER      DEFAULT 1,
    status          VARCHAR(16)  DEFAULT 'enabled',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_upc_user_id ON user_provider_channels(user_id);

-- =============================================================================
-- 5. 用户模型映射
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_model_mappings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_key       VARCHAR(128) NOT NULL,
    model_name      VARCHAR(256) NOT NULL,
    channel_id      UUID REFERENCES user_provider_channels(id) ON DELETE SET NULL,
    model_type      INTEGER      NOT NULL,
    priority        INTEGER      DEFAULT 0,
    status          VARCHAR(16)  DEFAULT 'enabled',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, model_key)
);

CREATE INDEX IF NOT EXISTS idx_umm_user_id ON user_model_mappings(user_id);

-- =============================================================================
-- 6. 项目注册表（项目内容仍保存在项目目录和项目级 SQLite 中）
-- =============================================================================
CREATE TABLE IF NOT EXISTS projects (
    id              VARCHAR(64) PRIMARY KEY,
    owner_type      VARCHAR(32)  NOT NULL,
    owner_id        VARCHAR(64)  NOT NULL,
    owner_username  VARCHAR(64)  NOT NULL,
    name            VARCHAR(255) NOT NULL,
    home_node_id    VARCHAR(64)  NOT NULL,
    output_dir      TEXT         NOT NULL,
    state_dir       TEXT         NOT NULL,
    runtime_dir     TEXT         NOT NULL,
    status          VARCHAR(32)  NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    purged_at       TIMESTAMPTZ,
    CONSTRAINT uq_projects_owner_name UNIQUE(owner_type, owner_id, name)
);

CREATE INDEX IF NOT EXISTS idx_projects_owner_id ON projects(owner_id);
CREATE INDEX IF NOT EXISTS idx_projects_owner_updated
    ON projects(owner_type, owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_status_updated
    ON projects(status, updated_at DESC);
