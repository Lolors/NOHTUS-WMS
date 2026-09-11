"""모바일 API 전용 토큰 인증.

로그인 자격 증명은 기존 Streamlit 앱과 완전히 동일한 users 테이블과
비밀번호 해시(nohtus.auth._hash_password)를 그대로 사용한다. 그래야
"스트림릿 유저 DB를 그대로 사용"이라는 요구사항이 실제로 성립한다.
발급하는 토큰은 이 API 전용의 별도 세션 테이블에 저장한다(Streamlit의
st.session_state와는 무관 — 모바일 API는 완전히 stateless HTTP다).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from nohtus.auth import _hash_password, ensure_auth_tables
from nohtus.db import connect, q

TOKEN_TTL_DAYS = 30


def ensure_mobile_session_table():
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_api_sessions(
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        con.commit()


def login(username: str, password: str):
    """성공 시 (token, user_dict)를, 실패 시 None을 반환."""
    ensure_auth_tables()
    ensure_mobile_session_table()

    username = (username or "").strip().lower()
    password = password or ""
    if not username or not password:
        return None

    df = q(
        "SELECT username, display_name, role, COALESCE(password_hash,'') AS password_hash "
        "FROM users WHERE COALESCE(active,1)=1 AND username=?",
        (username,),
    )
    if df.empty:
        return None
    row = df.iloc[0]
    password_hash = str(row.get("password_hash") or "")
    if not password_hash:
        # 스트림릿 쪽에서 아직 첫 비밀번호를 설정하지 않은 계정 — 모바일에서는 최초 설정을 지원하지 않는다.
        return None
    if _hash_password(username, password) != password_hash:
        return None

    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(days=TOKEN_TTL_DAYS)
    with connect() as con:
        con.execute(
            "INSERT INTO mobile_api_sessions(token, username, created_at, expires_at) VALUES (?,?,?,?)",
            (token, username, now.strftime("%Y-%m-%d %H:%M:%S"), expires.strftime("%Y-%m-%d %H:%M:%S")),
        )
        con.commit()

    user = {
        "username": username,
        "display_name": str(row.get("display_name") or username),
        "role": str(row.get("role") or "user"),
    }
    return token, user


def resolve_token(token: str):
    """유효한 토큰이면 user dict를, 아니면 None을 반환."""
    if not token:
        return None
    ensure_mobile_session_table()
    df = q(
        "SELECT s.username AS username, s.expires_at AS expires_at, "
        "u.display_name AS display_name, u.role AS role "
        "FROM mobile_api_sessions s JOIN users u ON u.username = s.username "
        "WHERE s.token=? AND COALESCE(u.active,1)=1",
        (token,),
    )
    if df.empty:
        return None
    row = df.iloc[0]
    try:
        expires_at = datetime.strptime(str(row["expires_at"]), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if expires_at < datetime.now():
        return None
    return {
        "username": str(row["username"]),
        "display_name": str(row["display_name"] or row["username"]),
        "role": str(row["role"] or "user"),
    }


def logout(token: str):
    if not token:
        return
    with connect() as con:
        con.execute("DELETE FROM mobile_api_sessions WHERE token=?", (token,))
        con.commit()
