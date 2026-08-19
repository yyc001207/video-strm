# syntax=docker/dockerfile:1

# ---------- 阶段 1：构建前端 ----------
FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend

# 先只拷贝依赖清单，充分利用 Docker 层缓存
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# 拷贝源码并构建（vue-tsc 类型检查 + vite build）
COPY frontend/ ./
RUN npm run build

# ---------- 阶段 2：后端运行时（前后端一体镜像） ----------
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# 前端构建产物：main.py 检测到 frontend/dist 后自动托管（含 SPA 回退）
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

# 数据与日志目录（建议挂载卷持久化，见 README「Docker 部署」）
RUN mkdir -p /app/data /app/openlist_logs
VOLUME ["/app/data", "/app/openlist_logs"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
