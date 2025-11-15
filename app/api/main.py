from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .scans import router as scans_router
from .search import router as search_router
from .proposals import router as proposals_router
from .audit import router as audit_router

app = FastAPI(
    title="本地截图行动归档 Agent",
    description="一个默认离线运行的桌面文件整理 Agent",
    version="0.1.0",
)

app.include_router(scans_router)
app.include_router(search_router)
app.include_router(proposals_router)
app.include_router(audit_router)

app.mount("/static", StaticFiles(directory="app/templates"), name="static")


@app.get("/")
async def root():
    return {"message": "本地截图行动归档 Agent"}
