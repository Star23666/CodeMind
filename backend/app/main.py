from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="CodeMind API",
        version="0.1.0",
        description="RAG knowledge base API for computer science learning.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"name": "CodeMind API", "status": "running"}

    return app


app = create_app()

