import sqlite3
import tempfile
import unittest
from pathlib import Path

import nohtus.services.master as master


def _create_tables(con):
    con.executescript(
        """
        CREATE TABLE inventory(
            id INTEGER PRIMARY KEY, company TEXT, product_name TEXT,
            warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT,
            qty INTEGER, updated_at TEXT
        );
        CREATE TABLE transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, actor TEXT,
            tx_type TEXT, product_name TEXT, warehouse_name TEXT, lot TEXT,
            exp_date TEXT, from_company TEXT, from_location TEXT,
            to_company TEXT, to_location TEXT, qty INTEGER, memo TEXT,
            final_stock INTEGER
        );
        """
    )


class UpdateInventoryMetadataExportWaitingSyncTests(unittest.TestCase):
    """수출대기 품목이 lot/유통기한 정정으로 사라진 재고행을 계속 가리키면
    수출확정 시 옛 lot/유통기한으로 재고를 찾다가 '재고가 부족합니다'
    오류가 난다. 정정/병합 시 export_waiting_items도 함께 갱신되어야 한다."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmpdir.name) / "test.db"
        with sqlite3.connect(self.db_path) as con:
            _create_tables(con)
            master.ensure_export_waiting_tables(con.cursor())
            con.commit()
        self._orig_connect = master.connect
        master.connect = lambda: sqlite3.connect(self.db_path)

    def tearDown(self):
        master.connect = self._orig_connect
        self._tmpdir.cleanup()

    def _seed_inventory(self, rows):
        with sqlite3.connect(self.db_path) as con:
            con.executemany("INSERT INTO inventory VALUES(?,?,?,?,?,?,?,?,?)", rows)

    def _seed_waiting_item(self, **cols):
        defaults = dict(
            id=1, order_id=1, source_inventory_id=0, company="노투스",
            product_name="제품A", warehouse_name="제품A", lot="LOTB",
            exp_date="2028-01-01", source_location="A1-01-01", waiting_location="P",
            qty=200, moved_at="2026-09-01 00:00:00", confirmed=0,
            confirmed_company=None, confirmed_customer_code=None,
            confirmed_customer_name=None, confirmed_at=None, waiting_inventory_id=1,
        )
        defaults.update(cols)
        with sqlite3.connect(self.db_path) as con:
            columns = ",".join(defaults.keys())
            placeholders = ",".join("?" for _ in defaults)
            con.execute(
                f"INSERT INTO export_waiting_items({columns}) VALUES({placeholders})",
                tuple(defaults.values()),
            )

    def _waiting_item(self):
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT waiting_inventory_id, lot, exp_date FROM export_waiting_items WHERE id=1"
            ).fetchone()
        return row

    def test_no_merge_correction_updates_referencing_waiting_item(self):
        self._seed_inventory([
            (1, "노투스", "제품A", "제품A", "LOTB", "2028-01-01", "P", 200, "2026-08-31"),
        ])
        self._seed_waiting_item(waiting_inventory_id=1, lot="LOTB", exp_date="2028-01-01")

        master.update_inventory_metadata(1, "LOTA", "2028-01-01")

        self.assertEqual(self._waiting_item(), (1, "LOTA", "2028-01-01"))

    def test_merge_correction_relinks_and_updates_waiting_item(self):
        self._seed_inventory([
            (1, "노투스", "제품A", "제품A", "LOTB", "2028-01-01", "P", 200, "2026-08-31"),
            (2, "노투스", "제품A", "제품A", "LOTA", "2028-01-01", "P", 50, "2026-08-31"),
        ])
        self._seed_waiting_item(waiting_inventory_id=1, lot="LOTB", exp_date="2028-01-01")

        master.update_inventory_metadata(1, "LOTA", "2028-01-01")

        self.assertEqual(self._waiting_item(), (2, "LOTA", "2028-01-01"))


if __name__ == "__main__":
    unittest.main()
