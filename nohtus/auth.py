from __future__ import annotations

import hashlib
from datetime import datetime

import streamlit as st

from nohtus.db import connect, q

DEFAULT_USERS = {
    "hn": {"display_name": "김한나", "role": "admin"},
    "jw": {"display_name": "김정욱", "role": "user"},
    "hj": {"display_name": "신호재", "role": "user"},
    "gw": {"display_name": "노건우", "role": "user"},
    "jg": {"display_name": "노진국", "role": "viewer"},
}

LEGACY_USERNAMES = ["khn", "kjw", "shj", "ngw", "njg"]

ROLE_PAGES = {
    "admin": None,
    "user": None,
    "viewer": {"로케이션 맵", "즐겨찾는 제품", "최근 조회"},
}


def _hash_password(username: str, password: str) -> str:
    raw = f"NOHTUS-WMS::{username}::{password}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def ensure_auth_tables():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        for legacy_username in LEGACY_USERNAMES:
            cur.execute("UPDATE users SET active=0, updated_at=? WHERE username=?", (now, legacy_username))
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
    return current_role() == "admin"


def logout():
    for key in ["current_user", "page"]:
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


def render_login():
    ensure_auth_tables()
    st.markdown("""
    <style>
    @media (min-width: 769px) {
        div[data-testid="stTextInput"],
        div[data-testid="stButton"],
        div[data-testid="stAlert"] {
            width: 20vw !important;
            min-width: 320px !important;
            max-width: 420px !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        div[data-testid="stTextInput"] > div,
        div[data-testid="stButton"] > button,
        div[data-testid="stAlert"] > div {
            width: 100% !important;
        }
        .login-caption-narrow {
            width: 20vw !important;
            min-width: 320px !important;
            max-width: 420px !important;
            margin-left: auto !important;
            margin-right: auto !important;
            color: #64748b;
            font-size: 0.875rem;
        }
    }
    @media (max-width: 768px) {
        div[data-testid="stTextInput"],
        div[data-testid="stButton"],
        div[data-testid="stAlert"],
        .login-caption-narrow {
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
        }
        div[data-testid="stTextInput"] > div,
        div[data-testid="stButton"] > button,
        div[data-testid="stAlert"] > div {
            width: 100% !important;
        }
    }
    </style>
    <div style="text-align:center; margin: 0.2rem 0 0.35rem 0;">
        <h1 style="margin:0; font-size:2.5rem; line-height:1.25; font-weight:700; color:#111827;">NOHTUS WMS 로그인</h1>
        <p style="margin:0.5rem 0 1.2rem 0; color:#64748b; font-size:0.95rem;">처음 접속하는 계정은 여기서 비밀번호를 설정합니다.</p>
    </div>
    """, unsafe_allow_html=True)

    username = st.text_input("아이디", key="login_username_input").strip().lower()
    row = _load_user(username) if username else None

    if username and row is None:
        st.error("존재하지 않는 계정입니다.")
        return False
    if row is None:
        return False

    st.markdown(
        f"<div class='login-caption-narrow'>계정 확인: {row.get('display_name')} ({row.get('role')})</div>",
        unsafe_allow_html=True,
    )
    password_hash = str(row.get("password_hash") or "")

    if not password_hash:
        st.info("첫 접속입니다. 사용할 비밀번호를 설정하세요.")
        p1 = st.text_input("새 비밀번호", type="password", key="first_password_1")
        p2 = st.text_input("새 비밀번호 확인", type="password", key="first_password_2")
        if st.button("비밀번호 설정 후 로그인", type="primary", use_container_width=True):
            if not p1 or len(p1) < 4:
                st.error("비밀번호는 4자 이상으로 설정하세요.")
                return False
            if p1 != p2:
                st.error("비밀번호 확인이 일치하지 않습니다.")
                return False
            new_hash = _hash_password(username, p1)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with connect() as con:
                con.execute("UPDATE users SET password_hash=?, updated_at=? WHERE username=?", (new_hash, now, username))
                con.commit()
            st.session_state["current_user"] = {"username": username, "display_name": str(row.get("display_name") or username), "role": str(row.get("role") or "user")}
            st.rerun()
    else:
        pw = st.text_input("비밀번호", type="password", key="login_password")
        if st.button("로그인", type="primary", use_container_width=True):
            if _hash_password(username, pw) != password_hash:
                st.error("비밀번호가 맞지 않습니다.")
                return False
            st.session_state["current_user"] = {"username": username, "display_name": str(row.get("display_name") or username), "role": str(row.get("role") or "user")}
            st.rerun()
    return False


def require_login():
    ensure_auth_tables()
    if get_current_user():
        return True
    render_login()
    return False


def render_user_box():
    user = get_current_user() or {}
    if not user:
        return
    st.sidebar.markdown("---")
    st.sidebar.caption(f"접속자: {user.get('display_name')} ({user.get('username')})")
    st.sidebar.caption(f"권한: {user.get('role')}")
    if st.sidebar.button("로그아웃", use_container_width=True):
        logout()
