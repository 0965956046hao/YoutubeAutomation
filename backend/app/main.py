import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import analyze, auth, config_router, facebook, videos

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("yt-recent-videos")

app = FastAPI(title="YT Recent Videos", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    from app.services.facebook_flow import restore_tasks

    restore_tasks()
    logger.info("YT Recent Videos starting on :%d (temp=%s)", settings.port, settings.temp_dir)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "yt-recent-videos"}


app.include_router(config_router.router, prefix="/api", tags=["config"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(videos.router, prefix="/api", tags=["videos"])
app.include_router(analyze.router, prefix="/api", tags=["analyze"])
app.include_router(facebook.router, prefix="/api", tags=["facebook"])
