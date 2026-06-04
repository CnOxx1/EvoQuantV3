-- EvoQuant PostgreSQL 初始化脚本
-- 容器首次启动时由 docker-entrypoint-initdb.d 自动执行

-- 创建三个 schema（对应原 SQLite 三库拆分）
CREATE SCHEMA IF NOT EXISTS exchange_data;
CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS analytics;

-- 赋予 evoquant 用户完整权限
GRANT ALL ON SCHEMA exchange_data TO evoquant;
GRANT ALL ON SCHEMA market_data TO evoquant;
GRANT ALL ON SCHEMA analytics TO evoquant;

-- 设置默认权限：evoquant 用户在这些 schema 中创建的表自动可访问
ALTER DEFAULT PRIVILEGES IN SCHEMA exchange_data GRANT ALL ON TABLES TO evoquant;
ALTER DEFAULT PRIVILEGES IN SCHEMA market_data GRANT ALL ON TABLES TO evoquant;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT ALL ON TABLES TO evoquant;
