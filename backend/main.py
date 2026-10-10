"""Kinship Archive —— FastAPI 入口。

职责：
  · 挂载 API（除 /api/health 外全部需要口令）
  · 托管前端构建产物 deploy/dist/（SPA 回退）
  · 托管 deploy/media/ 下的图片（带口令）

★ 隐私：本文件不含任何路径/口令硬编码，全部来自 deploy/config.toml 与 deploy/.env。
"""
from __future__ import annotations

import hmac
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .config import settings
from .routers import core, insight, public, records
from .routers import media as media_api
from .routers import wardrobe as wardrobe_api

app = FastAPI(
    title=settings.app_title,
    version="0.1.0",
    description="通用关系档案系统 —— 任意关系、统一时间轴、模块按人开关。",
)

# 开发模式：Vite dev server 跨端口访问 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ★ 手机经 Tailscale（走 DERP 中继，单程 RTT ~400ms）访问时，
#   首屏 531KB 未压缩的 JS/CSS 是最贵的一段。开 gzip 后 ~175KB（3x）。
#   minimum_size=1024：小响应（/api/persons 等）不值得压缩，省 CPU。
#   compresslevel=6：9 级对 200KB 的包要几十毫秒 CPU 且收益 <1%，不值。
#   默认的 exclude_content_types 已排除 image/*、video/*、zip、woff2 ——
#   媒体文件不会被二次编码（浪费 CPU 且可能坏 ETag）。
#   ★ 该中间件必须最后添加（= 最外层），这样它拿到的是内层已经写好
#     Cache-Control 的响应，压缩只改 body 与 Content-Encoding/Vary。
app.add_middleware(
    GZipMiddleware,
    minimum_size=1024,
    compresslevel=6,
)


def require_token(request: Request) -> None:
    """页面口令校验。支持三种携带方式：
    Authorization: Bearer xxx / X-Archive-Token: xxx / ?token=xxx（给 <img> 用）。"""
    if not settings.token:
        return  # 未配置口令：开发模式放行（/api/health 里会提示 auth_required=false）
    supplied = request.headers.get("X-Archive-Token") or ""
    auth = request.headers.get("Authorization") or ""
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    if not supplied:
        supplied = request.query_params.get("token", "")
    if not supplied:
        supplied = request.cookies.get("kinship_token", "")
    if not hmac.compare_digest(supplied, settings.token):
        raise HTTPException(status_code=401, detail="口令无效或缺失")


def media_token_ok(request: Request, query_token: Optional[str] = None) -> None:
    """媒体文件鉴权：Cookie / 请求头 / 查询串三选一。

    ★ 口令**不该出现在 URL 路径里** —— 那会让它进浏览器历史、Referer 头，
      以及 nginx/Cloudflare 的访问日志。现在登录时下发 Cookie，<img> 自动带上。
      查询串方式仅为兼容保留（会被日志记到，尽量别用）。
    """
    if not settings.token:
        return
    supplied = (
        request.cookies.get("kinship_token")
        or request.headers.get("X-Archive-Token")
        or query_token
        or ""
    )
    if not hmac.compare_digest(supplied, settings.token):
        raise HTTPException(status_code=401, detail="口令无效")


@app.exception_handler(ValueError)
async def _value_error_handler(_request: Request, exc: ValueError):  # pragma: no cover
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.middleware("http")
async def _cache_headers(request: Request, call_next):
    """缓存策略 —— 这直接决定「重新部署后手机能不能拿到新版本」。

    ★ SPA 入口 index.html 必须 no-cache：前端资源名带内容哈希，
      但 index.html 若被浏览器启发式缓存，手机会一直跑旧 JS（踩过）。
    """
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/media/"):
        resp.headers["Cache-Control"] = "private, max-age=86400"
    elif not path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


# 公共（无需口令）
app.include_router(public.router)

# 需要口令
auth = [Depends(require_token)]
app.include_router(core.router, dependencies=auth)
app.include_router(records.router, dependencies=auth)
app.include_router(wardrobe_api.router, dependencies=auth)
app.include_router(insight.router, dependencies=auth)
app.include_router(media_api.router, dependencies=auth)


# ---------------------------------------------------------------- 媒体文件

@app.get("/media/{path:path}")
def media_file(path: str, request: Request, token: Optional[str] = None):
    """图片/视频。鉴权走 Cookie（登录时下发）/ 请求头 —— 路径里不再带口令。"""
    media_token_ok(request, token)
    root = settings.media_path
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    ctype, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=ctype or "application/octet-stream")


# ---------------------------------------------------------------- 前端 SPA

def _mount_frontend() -> None:
    dist = settings.dist_path
    if not dist.is_dir():
        @app.get("/")
        def _no_frontend():
            return JSONResponse({
                "detail": "前端尚未构建。开发用 `cd frontend && npm run dev`，"
                          "生产用 `npm run build` 输出到 deploy/dist/。",
                "api_docs": "/docs",
            })
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    index = dist / "index.html"

    @app.get("/")
    def _index():
        return FileResponse(index)

    @app.get("/{path:path}")
    def _spa(path: str):
        """先找真实文件（favicon、manifest…），否则交给前端路由。"""
        candidate = (dist / path).resolve()
        if str(candidate).startswith(str(dist)) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


_mount_frontend()


@app.on_event("startup")
def _startup_banner() -> None:  # pragma: no cover - 日志
    print("[kinship-archive] 启动：%s:%s" % (settings.host, settings.port))
    print("[kinship-archive] 部署目录：%s" % settings.deploy_dir)
    print("[kinship-archive] 配置：%s" % (settings.config_path or "未找到 config.toml"))
    print("[kinship-archive] 口令：%s" % ("已启用" if settings.token else "未设置（开发模式）"))
    print("[kinship-archive] 前端产物：%s" % ("已就绪" if settings.dist_path.is_dir() else "缺失"))
