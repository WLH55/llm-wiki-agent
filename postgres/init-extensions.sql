-- ParadeDB 镜像内置 pg_search（BM25 + chinese_lindera 中文分词）+ pgvector
-- zhparser 已废弃（ADR-0019），由 pg_search 的 chinese_lindera 替代
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;
