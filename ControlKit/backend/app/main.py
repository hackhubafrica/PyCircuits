from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.analyze import router
from app.routers.design import router as design_router

app = FastAPI(title="ControlLens", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(design_router)


@app.get("/health")
def health():
    return {"status": "ok"}
