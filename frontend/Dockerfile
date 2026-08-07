# syntax=docker/dockerfile:1

# =============================================================================
# LLM Wiki Agent - Frontend 生产镜像
# 设计规范参考 WeKnora frontend/Dockerfile：
#   * 多阶段构建：Node 构建静态产物 -> Nginx 运行
#   * nginx 配置为模板，启动时经 envsubst 注入运行时配置（反代地址/上传大小）
#   * 生产 API 走 nginx 反代 /api -> backend，无需前端编译期环境变量
# =============================================================================

# ---------------- Stage 1: builder（Vite 构建） ----------------
FROM node:20-alpine AS builder

WORKDIR /build

# 依赖层缓存：package-lock.json 不变则跳过 npm ci
COPY package.json package-lock.json* ./
RUN npm ci

# 构建静态产物（tsc 类型检查 + vite build）
COPY . .
RUN npm run build

# ---------------- Stage 2: runtime（nginx） ----------------
# 固定补丁版本（nginx 1.27.x 系列），保证行为可预期；
# 如需完全可复现可换为 docker manifest inspect 得到的 digest 锁定
FROM nginx:1.27.4-alpine

# 拷贝构建产物 + nginx 模板 + 启动脚本
COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# 默认上传大小（与后端 PARSER_MAX_FILE_BYTES=50MiB 对齐，可经 compose 覆盖）
ENV MAX_FILE_SIZE_MB=50

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
