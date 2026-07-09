from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta

import streamlit as st

try:
    from streamlit_cookies_manager import EncryptedCookieManager
except Exception:  # pragma: no cover - optional dependency 안내용
    EncryptedCookieManager = None

from nohtus.db import connect, q

DEFAULT_USERS = {
    "hn": {"display_name": "김한나", "role": "admin"},
    "jw": {"display_name": "김정욱", "role": "user"},
    "hj": {"display_name": "신호재", "role": "user"},
    "gw": {"display_name": "노건우", "role": "user"},
    "jg": {"display_name": "노진국", "role": "viewer"},
}

ADMIN_USERNAMES = {"hn", "admin"}
LEGACY_USERNAMES = ["khn", "kjw", "shj", "ngw", "njg"]

ROLE_PAGES = {
    "admin": None,
    "user": None,
    "viewer": {"로케이션 맵", "유통기한 임박", "자사제품 조회", "전체 조회"},
}

REMEMBER_COOKIE_KEY = "remember_login_token"
REMEMBER_COOKIE_PREFIX = "nohtus_wms/"
REMEMBER_DAYS = 30
COOKIE_PASSWORD_ENV = "NOHTUS_COOKIE_SECRET"
COOKIE_PASSWORD_FALLBACK = "NOHTUS-WMS-remember-login-cookie-v1"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _expires_str(days: int = REMEMBER_DAYS) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _hash_password(username: str, password: str) -> str:
    raw = f"NOHTUS-WMS::{username}::{password}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _hash_login_token(token: str) -> str:
    raw = f"NOHTUS-WMS-LOGIN-TOKEN::{token}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _get_cookie_manager():
    if EncryptedCookieManager is None:
        return None
    if "_nohtus_cookie_manager" not in st.session_state:
        st.session_state["_nohtus_cookie_manager"] = EncryptedCookieManager(
            prefix=REMEMBER_COOKIE_PREFIX,
            password=os.environ.get(COOKIE_PASSWORD_ENV, COOKIE_PASSWORD_FALLBACK),
        )
    cookies = st.session_state["_nohtus_cookie_manager"]
    if not cookies.ready():
        st.stop()
    return cookies


def _delete_remember_cookie():
    cookies = _get_cookie_manager()
    if cookies is None:
        return
    if REMEMBER_COOKIE_KEY in cookies:
        del cookies[REMEMBER_COOKIE_KEY]
        cookies.save()


def ensure_auth_tables():
    now = _now_str()
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users(
                username TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        user_cols = {r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
        for col, ddl in {
            "display_name": "TEXT",
            "role": "TEXT",
            "password_hash": "TEXT",
            "active": "INTEGER DEFAULT 1",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        }.items():
            if col not in user_cols:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS login_tokens(
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT,
                last_used_at TEXT
            )
            """
        )
        cur.execute("DELETE FROM login_tokens WHERE expires_at < ?", (now,))

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS favorite_products(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                product_name TEXT NOT NULL,
                created_at TEXT,
                UNIQUE(username, product_name)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS recent_product_views(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                product_name TEXT NOT NULL,
                viewed_at TEXT,
                UNIQUE(username, product_name)
            )
            """
        )
        for username, info in DEFAULT_USERS.items():
            exists = cur.execute("SELECT username FROM users WHERE username=?", (username,)).fetchone()
            if not exists:
                cur.execute(
                    "INSERT OR IGNORE INTO users(username, display_name, role, password_hash, active, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                    (username, info["display_name"], info["role"], "", 1, now, now),
                )
            else:
                cur.execute(
                    "UPDATE users SET display_name=?, role=?, active=1, updated_at=? WHERE username=?",
                    (info["display_name"], info["role"], now, username),
                )
        for old_username in LEGACY_USERNAMES:
            cur.execute("DELETE FROM users WHERE username=?", (old_username,))
            cur.execute("DELETE FROM favorite_products WHERE username=?", (old_username,))
            cur.execute("DELETE FROM recent_product_views WHERE username=?", (old_username,))
            cur.execute("DELETE FROM login_tokens WHERE username=?", (old_username,))
            try:
                cur.execute("DELETE FROM mobile_favorite_products WHERE username=?", (old_username,))
            except Exception:
                pass
        con.commit()


def get_current_user():
    return st.session_state.get("current_user") or None


def current_username():
    user = get_current_user() or {}
    return str(user.get("username") or "")


def current_display_name():
    user = get_current_user() or {}
    return str(user.get("display_name") or "")


def current_role():
    user = get_current_user() or {}
    return str(user.get("role") or "")


def allowed_pages_for_current_user():
    return ROLE_PAGES.get(current_role())


def can_access_page(page_name: str) -> bool:
    pages = allowed_pages_for_current_user()
    return pages is None or page_name in pages


def is_admin():
    return current_role().strip().lower() == "admin" or current_username().strip().lower() in ADMIN_USERNAMES


def _user_dict_from_row(username: str, row) -> dict:
    return {
        "username": username,
        "display_name": str(row.get("display_name") or username),
        "role": str(row.get("role") or "user"),
    }


def _save_remember_login(username: str):
    cookies = _get_cookie_manager()
    if cookies is None:
        st.session_state["login_cookie_warning"] = "로그인 유지를 사용하려면 streamlit-cookies-manager 설치가 필요합니다."
        return

    token = secrets.token_urlsafe(32)
    token_hash = _hash_login_token(token)
    now = _now_str()
    expires_at = _expires_str()
    with connect() as con:
        con.execute(
            "INSERT INTO login_tokens(token_hash, username, expires_at, created_at, last_used_at) VALUES(?,?,?,?,?)",
            (token_hash, username, expires_at, now, now),
        )
        con.commit()
    cookies[REMEMBER_COOKIE_KEY] = token
    cookies.save()


def _login_user(username: str, row, remember_login: bool = False):
    st.session_state["current_user"] = _user_dict_from_row(username, row)
    if remember_login:
        _save_remember_login(username)


def _restore_login_from_cookie() -> bool:
    cookies = _get_cookie_manager()
    if cookies is None:
        return False

    token = cookies.get(REMEMBER_COOKIE_KEY)
    if not token:
        return False

    token_hash = _hash_login_token(str(token))
    df = q(
        """
        SELECT t.username, u.display_name, u.role
        FROM login_tokens t
        JOIN users u ON u.username = t.username
        WHERE t.token_hash=?
          AND t.expires_at >= ?
          AND COALESCE(u.active,1)=1
        """,
        (token_hash, _now_str()),
    )
    if df.empty:
        _delete_remember_cookie()
        return False

    row = df.iloc[0]
    username = str(row.get("username") or "").strip().lower()
    if not username:
        _delete_remember_cookie()
        return False

    st.session_state["current_user"] = _user_dict_from_row(username, row)
    with connect() as con:
        con.execute("UPDATE login_tokens SET last_used_at=? WHERE token_hash=?", (_now_str(), token_hash))
        con.commit()
    return True


def logout():
    cookies = _get_cookie_manager()
    token = cookies.get(REMEMBER_COOKIE_KEY) if cookies is not None else None
    if token:
        with connect() as con:
            con.execute("DELETE FROM login_tokens WHERE token_hash=?", (_hash_login_token(str(token)),))
            con.commit()
    _delete_remember_cookie()
    for key in ["current_user", "page", "login_cookie_warning"]:
        st.session_state.pop(key, None)
    st.rerun()


def _load_user(username: str):
    username = str(username or "").strip().lower()
    if not username:
        return None
    df = q("SELECT username, display_name, role, COALESCE(password_hash,'') AS password_hash FROM users WHERE COALESCE(active,1)=1 AND username=?", (username,))
    if df.empty:
        return None
    return df.iloc[0]


def _login_notice(message: str):
    if not message:
        return
    st.markdown(
        f"<div class='login-notice'>{message}</div>",
        unsafe_allow_html=True,
    )


def render_login():
    ensure_auth_tables()
    st.markdown("""
    <style>
    @media (min-width: 769px) {
        div[data-testid="stTextInput"],
        div[data-testid="stCheckbox"],
        div[data-testid="stButton"],
        div[data-testid="stFormSubmitButton"],
        div[data-testid="stForm"] {
            width: 20vw !important;
            max-width: 420px !important;
            min-width: 320px !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        div[data-testid="stForm"] {
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
        div[data-testid="stForm"] > div {
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
    }
    @media (max-width: 768px) {
        div[data-testid="stTextInput"],
        div[data-testid="stCheckbox"],
        div[data-testid="stButton"],
        div[data-testid="stFormSubmitButton"],
        div[data-testid="stForm"] {
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
        }
    }
    div[data-testid="stAlert"] {display:none !important;}
    .login-title {text-align:center;margin-top:1.2rem;margin-bottom:1.2rem;font-size:2.2rem;font-weight:700;}
    .login-account {text-align:center;color:#64748b;margin:0.25rem auto 0.9rem;font-size:0.92rem;}
    .login-notice {width:20vw;max-width:420px;min-width:320px;margin:8px auto 0 auto;color:#64748b;font-size:0.9rem;text-align:center;}
    @media (max-width: 768px) {.login-notice{width:100%;max-width:100%;min-width:0;}}
    </style>
    """, unsafe_allow_html=True)
    st.markdown("<div class='login-title'>NOHTUS WMS 로그인</div>", unsafe_allow_html=True)

    warning = st.session_state.pop("login_cookie_warning", "")
    if warning:
        _login_notice(warning)

    username = st.text_input("아이디", key="login_username_input").strip().lower()
    row = _load_user(username) if username else None

    # 입력 중에는 존재하지 않는 계정 경고를 표시하지 않는다.
    # 제출 후에도 빨간 alert 대신 작은 일반 안내문으로 처리한다.
    if row is None:
        with st.form("login_form_unknown_user", clear_on_submit=False):
            pw = st.text_input("비밀번호", type="password", key="login_password_unknown")
            st.checkbox("로그인 유지", key="remember_login_unknown")
            submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)
        if submitted:
            if not username:
                _login_notice("아이디를 입력하세요.")
            else:
                _login_notice("아이디 또는 비밀번호가 맞지 않습니다.")
        return False

    st.markdown(
        f"<div class='login-account'>계정 확인: {row.get('display_name')} ({row.get('role')})</div>",
        unsafe_allow_html=True,
    )
    password_hash = str(row.get("password_hash") or "")

    if not password_hash:
        _login_notice("첫 접속입니다. 사용할 비밀번호를 설정하세요.")
        with st.form("first_password_form", clear_on_submit=False):
            p1 = st.text_input("새 비밀번호", type="password", key="first_password_1")
            p2 = st.text_input("새 비밀번호 확인", type="password", key="first_password_2")
            remember_login = st.checkbox("로그인 유지", key="remember_login_first")
            submitted = st.form_submit_button("비밀번호 설정 후 로그인", type="primary", use_container_width=True)
        if submitted:
            if not p1 or len(p1) < 4:
                _login_notice("비밀번호는 4자 이상으로 설정하세요.")
                return False
            if p1 != p2:
                _login_notice("비밀번호 확인이 일치하지 않습니다.")
                return False
            new_hash = _hash_password(username, p1)
            now = _now_str()
            with connect() as con:
                con.execute("UPDATE users SET password_hash=?, updated_at=? WHERE username=?", (new_hash, now, username))
                con.commit()
            _login_user(username, row, remember_login=remember_login)
            return True
    else:
        with st.form("login_form", clear_on_submit=False):
            pw = st.text_input("비밀번호", type="password", key="login_password")
            remember_login = st.checkbox("로그인 유지", key="remember_login")
            submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)
        if submitted:
            if _hash_password(username, pw) != password_hash:
                _login_notice("아이디 또는 비밀번호가 맞지 않습니다.")
                return False
            _login_user(username, row, remember_login=remember_login)
            return True
    return False


def require_login():
    ensure_auth_tables()
    if get_current_user():
        return True
    if _restore_login_from_cookie():
        return True
    return render_login()


def render_user_box():
    user = get_current_user() or {}
    if not user:
        return
    st.sidebar.markdown("---")
    st.sidebar.caption(f"접속자: {user.get('display_name')} ({user.get('username')})")
    st.sidebar.caption(f"권한: {user.get('role')}")
    if st.sidebar.button("로그아웃", use_container_width=True):
        logout()
