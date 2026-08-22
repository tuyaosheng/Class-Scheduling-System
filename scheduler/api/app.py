from fastapi import FastAPI

from .routes import router as rest_router
from .ws import ws_router

app = FastAPI(title="排课系统 API")
app.include_router(rest_router)
app.include_router(ws_router)
