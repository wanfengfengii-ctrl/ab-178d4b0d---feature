# syntax=docker/dockerfile:1

# ---- 阶段 1: 前端依赖安装与生产构建 ----
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 阶段 2: 生产运行时 (FastAPI 托管前端构建产物) ----
FROM python:3.11-slim-bookworm AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ /app/backend/
COPY tests/ /app/tests/
COPY pytest.ini /app/pytest.ini
COPY scripts/ /app/scripts/
COPY --from=frontend /app/frontend/dist /app/frontend/dist
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- 阶段 3: verify 一次性服务 (测试 + 前端构建 + API 冒烟) ----
FROM node:22-bookworm-slim AS verify
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:$PATH"
# verify 阶段需要同时具备 Node(前端构建) 与 Python(pytest + uvicorn)。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /app/.venv
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r backend/requirements.txt
# 前端依赖: verify 要求真实执行一次前端构建。
COPY frontend/package.json frontend/package-lock.json /app/frontend/
RUN cd /app/frontend && npm ci --no-audit --no-fund
COPY frontend/ /app/frontend/
COPY backend/ /app/backend/
COPY tests/ /app/tests/
COPY pytest.ini /app/pytest.ini
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/verify.sh
CMD ["bash", "/app/scripts/verify.sh"]
