# 前端开发镜像（Vite dev server；源码由 compose 挂载）
FROM node:20-alpine

WORKDIR /app

# 先装依赖，利用层缓存
COPY package.json package-lock.json* ./
RUN npm ci || npm install

# 默认拷贝源码；compose 开发态会再挂载覆盖
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
