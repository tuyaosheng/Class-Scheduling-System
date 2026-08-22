"""FastAPI 应用入口。

本地开发模式运行：
    uvicorn scheduler.api.app:app --reload --port 8000
或在 PyCharm 里直接运行本文件。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router as rest_router
from .ws import ws_router

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
