#!/bin/sh
# =============================================================================
# Frontend 容器入口（参考 WeKnora frontend/docker-entrypoint.sh）
#   * 导出 nginx 模板所需运行时变量（反代地址、上传大小）
#   * envsubst 渲染模板 -> 写入 nginx 配置
#   * 前台启动 nginx
# =============================================================================
set -e

# 上传大小：MAX_FILE_SIZE_MB=50 -> 50M（与后端 PARSER_MAX_FILE_BYTES 对齐）
export MAX_FILE_SIZE=${MAX_FILE_SIZE_MB:-50}M
# 后端反代地址：容器内走服务名 backend；远程部署可经 compose 覆盖
export APP_HOST=${APP_HOST:-backend}
export APP_PORT=${APP_PORT:-8008}
export APP_SCHEME=${APP_SCHEME:-http}

# 渲染 nginx 模板
envsubst '${MAX_FILE_SIZE} ${APP_HOST} ${APP_PORT} ${APP_SCHEME}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

# 前台启动 nginx
exec nginx -g 'daemon off;'
