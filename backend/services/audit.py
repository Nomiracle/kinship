"""写入留痕：所有写操作都记一条，便于追溯「这个事实是谁、什么时候、从哪来的」。

不记录字段内容（避免把敏感数据再抄一份），只记实体与动作。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models import AuditLog


def write_audit(session: Session, entity: str, entity_id: Optional[int],
                action: str, source: str = "web") -> None:
    session.add(AuditLog(entity=entity, entity_id=entity_id, action=action, source=source))
