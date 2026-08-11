-- =============================================================================
-- 002_seed.sql: 初始种子数据
-- 默认管理员账号（首次部署时自动创建）
-- 用户名: admin  密码: admin123
-- 请在首次登录后立即修改密码！
-- =============================================================================

INSERT INTO users (id, username, password_hash, role, status, display_name)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'admin',
    '$2b$10$apdHiSzDO4aqBex/GOfvXuk5R.Om2pd9dVYQOii4JBuE.XHCFFewy',
    'owner',
    'active',
    'Administrator'
)
ON CONFLICT (username) DO NOTHING;

-- 为 admin 创建默认模型配置
INSERT INTO user_model_configs (user_id, gateway_mode)
VALUES ('00000000-0000-0000-0000-000000000001', 'official')
ON CONFLICT (user_id) DO NOTHING;