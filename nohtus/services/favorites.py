from __future__ import annotations

from datetime import datetime

from nohtus.db import connect, q


def list_favorites(username: str):
    username = str(username or "").strip()
    if not username:
        return []
    df = q("SELECT product_name FROM favorite_products WHERE username=? ORDER BY product_name", (username,))
    if df.empty:
        return []
    return df["product_name"].dropna().astype(str).tolist()


def is_favorite(username: str, product_name: str) -> bool:
    username = str(username or "").strip()
    product_name = str(product_name or "").strip()
    if not username or not product_name:
        return False
    df = q("SELECT 1 FROM favorite_products WHERE username=? AND product_name=? LIMIT 1", (username, product_name))
    return not df.empty


def add_favorite(username: str, product_name: str):
    username = str(username or "").strip()
    product_name = str(product_name or "").strip()
    if not username or not product_name:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO favorite_products(username, product_name, created_at) VALUES(?,?,?)", (username, product_name, now))
        con.commit()


def remove_favorite(username: str, product_name: str):
    username = str(username or "").strip()
    product_name = str(product_name or "").strip()
    if not username or not product_name:
        return
    with connect() as con:
        con.execute("DELETE FROM favorite_products WHERE username=? AND product_name=?", (username, product_name))
        con.commit()


def toggle_favorite(username: str, product_name: str) -> bool:
    if is_favorite(username, product_name):
        remove_favorite(username, product_name)
        return False
    add_favorite(username, product_name)
    return True


def record_recent_view(username: str, product_name: str):
    username = str(username or "").strip()
    product_name = str(product_name or "").strip()
    if not username or not product_name:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        con.execute(
            """
            INSERT INTO recent_product_views(username, product_name, viewed_at)
            VALUES(?,?,?)
            ON CONFLICT(username, product_name)
            DO UPDATE SET viewed_at=excluded.viewed_at
            """,
            (username, product_name, now),
        )
        con.commit()


def list_recent_views(username: str, limit: int = 10):
    username = str(username or "").strip()
    if not username:
        return []
    df = q("SELECT product_name FROM recent_product_views WHERE username=? ORDER BY viewed_at DESC LIMIT ?", (username, int(limit)))
    if df.empty:
        return []
    return df["product_name"].dropna().astype(str).tolist()
