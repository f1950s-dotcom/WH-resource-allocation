from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import master, volume, optimize, shift

app = FastAPI(
    title="倉庫人員配置最適化システム API",
    description="Warehouse Resource Allocation Optimization System",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
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
