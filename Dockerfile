# ---- フロントエンド(Vite)ビルド ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# 本番は同一オリジンでAPIを叩くため、APIのベースURLは空(相対パス /api/...)にする
ENV VITE_API_URL=""
RUN npm run build

# ---- バックエンド(FastAPI)実行イメージ ----
FROM python:3.11-slim AS runtime
WORKDIR /app

# OR-Tools等のためのランタイム依存
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
# ビルド済みフロントを配信用ディレクトリへ
COPY --from=frontend /app/frontend/dist ./frontend/dist

# 永続SQLiteの保存先（Flyのボリュームを /data にマウントする）
ENV DATABASE_URL="sqlite:////data/warehouse.db"
ENV FRONTEND_DIST="/app/frontend/dist"
ENV PORT=8080

WORKDIR /app/backend
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
