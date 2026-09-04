"""임시저장 발주서와 품목의 SQLite 데이터 접근 Repository."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from db_migration import normalize_product_code

DRAFT_COLUMNS = ["임시ID", "작성일시", "거래처명", "요청사항", "상태", "총품목수", "총수량"]
DRAFT_ITEM_COLUMNS = ["임시ID", "순번", "제품코드", "정식제품명", "검색별칭", "규격", "단위", "수량"]
DRAFT_MIGRATION_KEY = "draft_csv_migration_v2"


class DraftRepository:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "purchase_order.db"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @staticmethod
    def _to_int(value: object) -> int:
        try:
            return int(float(str(value or "0").replace(",", "")))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame(columns=columns)
        frame = pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")
        for column in columns:
            if column not in frame.columns:
                frame[column] = ""
        return frame[columns]

    def migrate_legacy_csv_once(self) -> bool:
        """최초 DB 전환 뒤 CSV에 추가된 임시저장 데이터를 한 번만 병합합니다."""
        drafts = self._read_csv(self.data_dir / "drafts.csv", DRAFT_COLUMNS)
        draft_items = self._read_csv(self.data_dir / "draft_items.csv", DRAFT_ITEM_COLUMNS)

        with self._connect() as conn:
            marker = conn.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                (DRAFT_MIGRATION_KEY,),
            ).fetchone()
            if marker:
                return False

            conn.execute("BEGIN IMMEDIATE")
            draft_ids = []
            for _, row in drafts.iterrows():
                draft_id = str(row.get("임시ID", "") or "").strip()
                if not draft_id:
                    continue
                draft_ids.append(draft_id)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO drafts(
                        draft_id, created_at, vendor_name, request_note, status,
                        total_item_count, total_quantity
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        draft_id,
                        str(row.get("작성일시", "") or ""),
                        str(row.get("거래처명", "") or ""),
                        str(row.get("요청사항", "") or ""),
                        str(row.get("상태", "") or "임시저장"),
                        self._to_int(row.get("총품목수", 0)),
                        self._to_int(row.get("총수량", 0)),
                    ),
                )

            for draft_id in set(draft_ids):
                conn.execute("DELETE FROM draft_items WHERE draft_id = ?", (draft_id,))

            rows = []
            for _, row in draft_items.iterrows():
                draft_id = str(row.get("임시ID", "") or "").strip()
                if not draft_id:
                    continue
                rows.append(
                    (
                        draft_id,
                        self._to_int(row.get("순번", 0)),
                        normalize_product_code(row.get("제품코드", "")),
                        str(row.get("정식제품명", "") or ""),
                        str(row.get("검색별칭", "") or ""),
                        str(row.get("규격", "") or ""),
                        str(row.get("단위", "") or ""),
                        self._to_int(row.get("수량", 0)),
                    )
                )
            if rows:
                conn.executemany(
                    """
                    INSERT INTO draft_items(
                        draft_id, sequence, product_code, product_name, search_alias,
                        specification, packaging_unit, quantity
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    rows,
                )

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT OR REPLACE INTO app_metadata(key,value,updated_at) VALUES(?,?,?)",
                (DRAFT_MIGRATION_KEY, now, now),
            )
            conn.commit()
        return True

    def load_all(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        with self._connect() as conn:
            headers = conn.execute(
                """
                SELECT draft_id, created_at, vendor_name, request_note, status,
                       total_item_count, total_quantity
                FROM drafts
                ORDER BY created_at DESC, draft_id DESC
                """
            ).fetchall()
            items = conn.execute(
                """
                SELECT draft_id, sequence, product_code, product_name, search_alias,
                       specification, packaging_unit, quantity
                FROM draft_items
                ORDER BY draft_id, sequence, id
                """
            ).fetchall()

        drafts = pd.DataFrame(headers, columns=DRAFT_COLUMNS).fillna("")
        draft_items = pd.DataFrame(items, columns=DRAFT_ITEM_COLUMNS).fillna("")
        if not draft_items.empty:
            draft_items["제품코드"] = draft_items["제품코드"].map(normalize_product_code)
        return drafts, draft_items

    def save(self, vendor_name: str, request_note: str, items: list[dict]) -> str:
        now = datetime.now().replace(microsecond=0)
        base_id = f"TEMP-{now.strftime('%Y%m%d-%H%M%S')}"
        total_count = len(items)
        total_qty = sum(self._to_int(item.get("수량", 0)) for item in items)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = {
                row[0]
                for row in conn.execute(
                    "SELECT draft_id FROM drafts WHERE draft_id LIKE ?",
                    (f"{base_id}%",),
                )
            }
            draft_id = base_id
            suffix = 2
            while draft_id in existing:
                draft_id = f"{base_id}-{suffix}"
                suffix += 1

            conn.execute(
                """
                INSERT INTO drafts(
                    draft_id, created_at, vendor_name, request_note, status,
                    total_item_count, total_quantity
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    draft_id,
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                    str(vendor_name or "").strip(),
                    str(request_note or ""),
                    "임시저장",
                    total_count,
                    total_qty,
                ),
            )

            rows = []
            for sequence, item in enumerate(items, 1):
                rows.append(
                    (
                        draft_id,
                        sequence,
                        normalize_product_code(item.get("제품코드", "")),
                        str(item.get("정식제품명", item.get("제품명", "")) or ""),
                        str(item.get("검색별칭", "") or ""),
                        str(item.get("규격", "") or ""),
                        str(item.get("단위", item.get("포장단위", "")) or ""),
                        self._to_int(item.get("수량", 0)),
                    )
                )
            if rows:
                conn.executemany(
                    """
                    INSERT INTO draft_items(
                        draft_id, sequence, product_code, product_name, search_alias,
                        specification, packaging_unit, quantity
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    rows,
                )
            conn.commit()
        return draft_id

    def delete(self, draft_id: str) -> None:
        draft_id = str(draft_id or "").strip()
        if not draft_id:
            raise ValueError("삭제할 임시ID가 없습니다.")

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM draft_items WHERE draft_id = ?", (draft_id,))
            conn.execute("DELETE FROM drafts WHERE draft_id = ?", (draft_id,))
            conn.commit()
