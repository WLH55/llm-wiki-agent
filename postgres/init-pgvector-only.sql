-- 开发默认镜像（pgvector/pgvector）初始化脚本。
-- 仅启用 vector；中文分词扩展需使用自定义 postgres Dockerfile 构建。
CREATE EXTENSION IF NOT EXISTS vector;
