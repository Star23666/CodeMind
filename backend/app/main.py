from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.core.config import settings
from app.services.document_job_service import document_job_service
from app.services.mind_map_job_service import mind_map_job_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await document_job_service.start()
    await mind_map_job_service.start()
    try:
        yield
    finally:
        await mind_map_job_service.stop()
        await document_job_service.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="CodeMind API",
        version="0.1.0",
        description="RAG knowledge base API for computer science learning.",
        lifespan=lifespan,
    )

    # ---------- 新增：中文验证错误处理 ----------
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            field = error["loc"][-1] if error["loc"] else "未知字段"
            msg = error["msg"]
            ctx = error.get("ctx", {})

            # 常见验证类型 → 中文提示
            if error["type"] in {"missing", "value_error.missing"}:
                msg = f"缺少必填字段：{field}"
            elif error["type"] == "string_too_short":
                msg = f"“{field}”长度不能少于{ctx.get('min_length', '?')}个字符"
            elif error["type"] == "string_too_long":
                msg = f"“{field}”长度不能超过{ctx.get('max_length', '?')}个字符"
            elif error["type"] in {"value_error.email", "value_error.email_address"}:
                msg = "邮箱格式不正确"
            # 其他类型可继续扩展...
            errors.append(msg)

        return JSONResponse(
            status_code=422,
            content={"detail": "；".join(errors)}
        )
    # ------------------------------------

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

