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
