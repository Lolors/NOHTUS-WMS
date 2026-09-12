"""모바일 API 전용 토큰 인증.

로그인 자격 증명은 기존 Streamlit 앱과 완전히 동일한 users 테이블과
비밀번호 해시(nohtus.auth._hash_password)를 그대로 사용한다. 그래야
"스트림릿 유저 DB를 그대로 사용"이라는 요구사항이 실제로 성립한다.
발급하는 토큰은 이 API 전용의 별도 세션 테이블에 저장한다(Streamlit의
st.session_state와는 무관 — 모바일 API는 완전히 stateless HTTP다).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from nohtus.auth import _hash_password, _needs_rehash, _verify_password, ensure_auth_tables
from nohtus.db import connect, q

TOKEN_TTL_DAYS = 30

# 로그인 무차별 대입 방어: 같은 아이디에 실패가 몰리면 그 아이디만 잠근다
# (사무실 공유 IP 하나 때문에 전체 직원이 한꺼번에 막히지 않도록, IP 기준
# 잠금 한도는 훨씬 넉넉하게 잡아서 "한 IP에서 여러 계정을 훑는" 공격만
# 잡아낸다). 존재하지 않는 아이디로 시도해도 동일하게 기록해서, 아이디
# 존재 여부 자체가 새어나가지 않게 한다.
FAILED_LOGIN_LIMIT_PER_USER = 5
FAILED_LOGIN_LIMIT_PER_IP = 20
FAILED_LOGIN_WINDOW_MINUTES = 15


class LoginLockedError(Exception):
    """짧은 시간 안에 로그인 실패가 너무 많이 몰렸을 때."""

    def __init__(self, retry_after_minutes: int):
        self.retry_after_minutes = retry_after_minutes
        super().__init__(f"too many failed login attempts, retry after {retry_after_minutes}m")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_login_attempts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip TEXT NOT NULL,
                success INTEGER NOT NULL,
                attempted_at TEXT NOT NULL
            )
            """
        )
        con.commit()


def _recent_failed_attempts(username: str, ip: str) -> tuple[int, int]:
    """(해당 아이디 실패 횟수, 해당 IP 실패 횟수)."""
    cutoff = (datetime.now() - timedelta(minutes=FAILED_LOGIN_WINDOW_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    df = q(
        "SELECT username, ip FROM mobile_login_attempts WHERE success=0 AND attempted_at>=? AND (username=? OR ip=?)",
        (cutoff, username, ip),
    )
    if df.empty:
        return 0, 0
    user_count = int((df["username"] == username).sum())
    ip_count = int((df["ip"] == ip).sum())
    return user_count, ip_count


def _record_login_attempt(username: str, ip: str, success: bool):
    now = datetime.now()
    # 오래된 시도 기록은 굳이 쌓아둘 필요 없으니 매번 정리한다(하루 이상 지난 것만).
    purge_before = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        con.execute("DELETE FROM mobile_login_attempts WHERE attempted_at<?", (purge_before,))
        con.execute(
            "INSERT INTO mobile_login_attempts(username, ip, success, attempted_at) VALUES (?,?,?,?)",
            (username, ip or "", 1 if success else 0, now.strftime("%Y-%m-%d %H:%M:%S")),
        )
        con.commit()


def login(username: str, password: str, ip: str = ""):
    """성공 시 (token, user_dict)를, 실패 시 None을 반환.

    실패가 너무 잦으면 LoginLockedError를 던진다.
    """
    ensure_auth_tables()
    ensure_mobile_session_table()

    username = (username or "").strip().lower()
    password = password or ""
    ip = ip or ""
    if not username or not password:
        return None

    user_fail_count, ip_fail_count = _recent_failed_attempts(username, ip)
    if user_fail_count >= FAILED_LOGIN_LIMIT_PER_USER or ip_fail_count >= FAILED_LOGIN_LIMIT_PER_IP:
        raise LoginLockedError(FAILED_LOGIN_WINDOW_MINUTES)

    df = q(
        "SELECT username, display_name, role, COALESCE(password_hash,'') AS password_hash "
        "FROM users WHERE COALESCE(active,1)=1 AND username=?",
        (username,),
    )
    if df.empty:
        _record_login_attempt(username, ip, False)
        return None
    row = df.iloc[0]
    password_hash = str(row.get("password_hash") or "")
    if not password_hash:
        # 스트림릿 쪽에서 아직 첫 비밀번호를 설정하지 않은 계정 — 모바일에서는 최초 설정을 지원하지 않는다.
        _record_login_attempt(username, ip, False)
        return None
    if not _verify_password(username, password, password_hash):
        _record_login_attempt(username, ip, False)
        return None

    if _needs_rehash(password_hash):
        with connect() as con:
            con.execute(
                "UPDATE users SET password_hash=? WHERE username=?",
                (_hash_password(username, password), username),
            )
            con.commit()

    _record_login_attempt(username, ip, True)

    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(days=TOKEN_TTL_DAYS)
    with connect() as con:
        con.execute(
            "INSERT INTO mobile_api_sessions(token, username, created_at, expires_at) VALUES (?,?,?,?)",
            (_hash_token(token), username, now.strftime("%Y-%m-%d %H:%M:%S"), expires.strftime("%Y-%m-%d %H:%M:%S")),
        )
        con.commit()

    user = {
        "username": username,
        "display_name": str(row.get("display_name") or username),
        "role": str(row.get("role") or "user"),
    }
    return token, user


def resolve_token(token: str):
    """유효한 토큰이면 user dict를, 아니면 None을 반환.

    DB에는 토큰 원문이 아니라 해시만 저장돼 있으므로, 여기서도 해시로
    변환해 조회한다 — DB가 유출돼도 토큰 원문이 그대로 도용되지 않는다.
    """
    if not token:
        return None
    ensure_mobile_session_table()
    df = q(
        "SELECT s.username AS username, s.expires_at AS expires_at, "
        "u.display_name AS display_name, u.role AS role "
        "FROM mobile_api_sessions s JOIN users u ON u.username = s.username "
        "WHERE s.token=? AND COALESCE(u.active,1)=1",
        (_hash_token(token),),
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
        con.execute("DELETE FROM mobile_api_sessions WHERE token=?", (_hash_token(token),))
        con.commit()
