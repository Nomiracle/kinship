"""持久幂等键服务（archive redesign backend lane）。

契约：
- 前端通过 Idempotency-Key header 在 POST /api/events, /api/outfits,
  /api/wardrobe/items, /api/media 上发送键，可选向后兼容。
- 服务端必须持久化 fingerprint+response 原子提交；409 处理不匹配重试；
  相同键回放原始状态/主体；禁止仅内存去重。
- Per-attachment stable keys：媒体层每个文件独立键。

实现：表格 idempotency_keys（唯一键）+ 逻辑在 routers 中通过
claim → 执行业务 → update response 的流程原子提交。
并发通过唯一约束 + SAVEPOINT 处理；REPEATABLE READ 下用当前读（FOR UPDATE）。
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import IdempotencyKey


def extract_key(request: Request) -> Optional[str]:
    k = request.headers.get("Idempotency-Key")
    if not k:
        k = request.headers.get("idempotency-key")
    if not k:
        for hk, hv in request.headers.items():
            if hk.lower() == "idempotency-key":
                k = hv
                break
    if not k:
        return None
    k = k.strip()
    if not k:
        return None
    if len(k) > 128:
        raise HTTPException(status_code=400, detail="Idempotency-Key too long")
    return k


def hash_payload(obj) -> str:
    try:
        canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        canonical = str(obj)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_media_fields(person_id, event_id, wardrobe_item_id, file_hashes, captured_on=None) -> str:
    payload = {
        "person_id": person_id,
        "event_id": event_id,
        "wardrobe_item_id": wardrobe_item_id,
        "files": sorted(file_hashes),
        "captured_on": str(captured_on) if captured_on else None,
    }
    return hash_payload(payload)


def _replay_response(rec: IdempotencyKey) -> JSONResponse:
    body = json.loads(rec.response_body) if rec.response_body else None
    return JSONResponse(status_code=rec.response_status or 200, content=body, headers={"Idempotent-Replayed": "true"})


def check_replay(session: Session, key: str, payload_hash: str, scope: Optional[str] = None):
    """若 key 已存在则校验或回放。返回 JSONResponse / None / raise 409."""
    rec = session.scalar(select(IdempotencyKey).where(IdempotencyKey.idempotency_key == key))
    if rec is None:
        return None
    if scope is not None and rec.scope != scope:
        raise HTTPException(status_code=409, detail={"message": "Idempotency-Key scope mismatch", "key": key, "expected_scope": scope, "actual_scope": rec.scope})
    if rec.request_hash != payload_hash:
        raise HTTPException(status_code=409, detail={"message": "Idempotency-Key already used with different payload", "key": key})
    if rec.response_body is not None:
        return _replay_response(rec)
    raise HTTPException(status_code=409, detail="Concurrent request with same Idempotency-Key in progress")


def try_claim(session: Session, key: str, scope: str, payload_hash: str):
    """尝试占位声明 key。成功返回占位行，否则处理并发并可能抛 409/回放。

    关键修复：
    - 占位插入必须在 SAVEPOINT 内部完成，避免 session.add 提前触发 autoflush 污染外层事务。
    - 唯一冲突后用当前读（SELECT ... FOR UPDATE）避免 MySQL REPEATABLE READ 快照不可见。
    - 校验 scope 与 request_hash 两个维度，避免跨 endpoint 重放。
    """
    # 尝试在嵌套事务内插入占位；成功则持有占位行，业务与 complete_claim 同一外层事务提交
    placeholder = None
    try:
        with session.begin_nested():
            placeholder = IdempotencyKey(
                idempotency_key=key,
                scope=scope,
                request_hash=payload_hash,
                response_status=None,
                response_body=None,
            )
            session.add(placeholder)
            session.flush()
        return placeholder
    except IntegrityError:
        # SAVEPOINT 已回滚，外层事务仍可用；需用当前读获取竞争者已提交的行
        pass

    # 当前读：FOR UPDATE 强制从最新已提交读取，绕开 REPEATABLE READ 快照
    try:
        existing = session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.idempotency_key == key).with_for_update()
        )
    except Exception:
        # SQLite 或不支持 FOR UPDATE 的 dialect 回退为普通查询
        existing = None
    if existing is None:
        # 回退或 FOR UPDATE 未返回时再试普通当前读（可能仍需一个 flush 来刷新快照）
        try:
            session.flush()
        except Exception:
            pass
        existing = session.scalar(select(IdempotencyKey).where(IdempotencyKey.idempotency_key == key))
    if existing is None:
        raise HTTPException(status_code=409, detail="Idempotency-Key conflict, retry")

    # 校验维度：scope + hash 都必须匹配才允许回放，否则 409
    if existing.scope != scope:
        raise HTTPException(status_code=409, detail={"message": "Idempotency-Key already used with different scope", "key": key, "expected_scope": scope, "actual_scope": existing.scope})
    if existing.request_hash != payload_hash:
        raise HTTPException(status_code=409, detail={"message": "Idempotency-Key already used with different payload", "key": key})
    if existing.response_body is not None:
        return _replay_response(existing)
    raise HTTPException(status_code=409, detail="Concurrent request with same Idempotency-Key in progress")


def complete_claim(session: Session, placeholder, status_code: int, body):
    """将占位行补全响应并 flush（与业务同一事务）。"""
    try:
        from fastapi.encoders import jsonable_encoder
        encoded = jsonable_encoder(body)
        body_json = json.dumps(encoded, ensure_ascii=False)
    except Exception:
        try:
            body_json = json.dumps(body, ensure_ascii=False, default=str)
        except Exception:
            body_json = json.dumps(str(body), ensure_ascii=False)
    placeholder.response_status = status_code
    placeholder.response_body = body_json
    session.flush()
