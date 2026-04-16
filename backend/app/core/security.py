from __future__ import annotations

import hashlib
from fastapi import Header, HTTPException

from app.db.database import db


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def require_token(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.replace("Bearer ", "", 1).strip()

    with db() as conn:
        row = conn.execute(
            '''
            SELECT u.id, u.email, u.full_name, u.plan, u.active
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            ''',
            (token,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid session token")

    return dict(row)\n