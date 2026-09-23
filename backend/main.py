"""FastAPI 应用: 档案片段重建台。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .schemas import ValidationError, parse_request
from .solver import solve

app = FastAPI(title="档案片段重建台", version="1.0.0")


@app.exception_handler(ValidationError)
async def validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
    # 统一 422 结构: {"detail": [{"loc": [...], "msg": ..., "type": ...}]}
    return JSONResponse(status_code=422, content={"detail": exc.errors})


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/reconstruct")
async def reconstruct(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        raise ValidationError(
            [{"loc": ["body"], "msg": "请求体为空", "type": "parse_error"}]
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            [
                {
                    "loc": ["body"],
                    "msg": f"不是合法 JSON: {exc.msg}",
                    "type": "parse_error",
                }
            ]
        )
    length, fragments = parse_request(payload)
    return solve(length, fragments).to_dict()


# 生产镜像中前端构建产物挂载到根路径; 开发时该目录不存在则跳过。
_STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _STATIC_DIR.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(_STATIC_DIR), html=True),
        name="frontend",
    )
