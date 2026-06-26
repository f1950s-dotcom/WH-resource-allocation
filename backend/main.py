import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from database import init_db
from routers import master, volume, optimize, shift

# MIPソルバーのステータス・ギャップ等、最適化のログ(INFO)を確実に出力する
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="倉庫人員配置最適化システム API",
    description="Warehouse Resource Allocation Optimization System",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    init_db()


# Routers
app.include_router(master.router, prefix="/api")
app.include_router(volume.router, prefix="/api")
app.include_router(optimize.router, prefix="/api")
app.include_router(shift.router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# --- フロントエンド(ビルド済みSPA)の配信 ---------------------------------
# 1サービスで公開できるよう、Viteのビルド成果物(frontend/dist)があれば
# FastAPIから静的配信する。APIは /api・/health が先に登録されているため、
# それ以外のパスはSPAとして index.html を返す（クライアントルーティング対応）。
_FRONTEND_DIST = os.getenv(
    "FRONTEND_DIST",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist"),
)

if os.path.isdir(_FRONTEND_DIST):
    _ASSETS_DIR = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(_ASSETS_DIR):
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

    _INDEX_HTML = os.path.join(_FRONTEND_DIST, "index.html")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request, exc):
        # 404かつAPI/ヘルス以外のGETはSPAのindex.htmlを返す
        path = request.url.path
        if (
            exc.status_code == 404
            and request.method == "GET"
            and not path.startswith("/api")
            and not path.startswith("/assets")
            and path != "/health"
        ):
            return FileResponse(_INDEX_HTML)
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.get("/")
    async def serve_index():
        return FileResponse(_INDEX_HTML)

    # ルート直下の静的ファイル(favicon等)も配信
    @app.get("/{filename:path}")
    async def serve_static_or_index(filename: str):
        candidate = os.path.join(_FRONTEND_DIST, filename)
        if filename and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_INDEX_HTML)
