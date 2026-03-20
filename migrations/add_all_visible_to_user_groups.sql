-- migrations/add_all_visible_to_user_groups.sql
-- 为 user_groups 表添加 all_visible 字段
-- 适用于 SQLite 和 PostgreSQL
-- 生产环境手动执行此脚本；开发环境 SQLite 内存库由 init_db() 自动建表

ALTER TABLE user_groups ADD COLUMN all_visible BOOLEAN DEFAULT FALSE;

-- 将现有 "default" 分组标记为全员可见（向后兼容：之前所有用户自动加入 default）
UPDATE user_groups SET all_visible = TRUE WHERE name = 'default';
