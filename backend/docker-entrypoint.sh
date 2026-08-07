#!/bin/bash
# =============================================================================
# Backend 容器入口（参考 WeKnora scripts/docker-entrypoint.sh）
#   * 以 root 启动，修复可能被 bind-mount 的目录属主（宿主 UID 与容器 appuser 不一致）
#   * 通过 gosu 降权为 appuser 后执行主进程（与官方 postgres/redis 镜像同款模式）
# =============================================================================
set -e

# 可能被 bind-mount 且需要 appuser 可写的目录（开发环境 ./storage 挂载）
MOUNT_DIRS=(
    /app/logs
    /app/storage
)

for dir in "${MOUNT_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || true
    fi
done

# 降权并执行主进程（CMD / compose command 原样透传）
exec gosu appuser "$@"
