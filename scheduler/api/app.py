"""FastAPI 应用入口。

本地开发模式运行：
    uvicorn scheduler.api.app:app --reload --port 8000
或直接运行本文件（PyCharm 里点运行按钮 / python scheduler/api/app.py）——
此时 sys.path 里没有项目根目录，import scheduler 会失败，所以先注入。
"""
import sys
from pathlib import Path

# 项目根目录 = 本文件 ../../ 目录（scheduler 包的父目录）。
# 直接运行本文件时把根目录加进 sys.path，否则绝对导入找不到 scheduler。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scheduler.api.routes import router as rest_router
from scheduler.api.ws import ws_router

app = FastAPI(title="排课系统 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_router)
app.include_router(ws_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("scheduler.api.app:app", host="127.0.0.1", port=8000, reload=True)
