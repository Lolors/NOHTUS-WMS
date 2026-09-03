import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import nohtus.services.export_waiting as export_waiting


def _create_tables(con):
    con.executescript(
        """
        CREATE TABLE inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT, product_name TEXT,
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


class RepairBrokenWaitingReservationsTests(unittest.TestCase):
    """일반 이동 등록으로 P 예약 재고가 몰래 다른 위치로 옮겨져 수출확정 시
    'P 로케이션 재고가 부족합니다' 오류가 나는 경우를 복구할 수 있어야 한다."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmpdir.name) / "test.db"
        with sqlite3.connect(self.db_path) as con:
            _create_tables(con)
            export_waiting.ensure_export_waiting_tables(con.cursor())
            con.commit()
        self._orig_connect = export_waiting.connect
        export_waiting.connect = lambda: sqlite3.connect(self.db_path)

    def tearDown(self):
        export_waiting.connect = self._orig_connect
        self._tmpdir.cleanup()

    def _seed(self, order_status="waiting"):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO export_waiting_orders(export_no,country,buyer,transport_method,title,status,created_at,updated_at,created_by)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                ("EXP-2026-024", "USA", "미지정", "미지정", "테스트건", order_status, now, now, "tester"),
            )
            order_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            con.execute(
                "INSERT INTO export_waiting_items(order_id,source_inventory_id,waiting_inventory_id,company,product_name,"
                "warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (order_id, 1, 1, "노투스", "오토 - DN MTS NEEDLE 12핀", "오토 - DN MTS NEEDLE 12핀",
                 "-", "-", "A1-01-01", "P", 200, now),
            )
            con.commit()
        return order_id

    def _inventory_rows(self):
        with sqlite3.connect(self.db_path) as con:
            return con.execute("SELECT id, location, qty FROM inventory ORDER BY id").fetchall()

    def _item(self):
        with sqlite3.connect(self.db_path) as con:
            return con.execute(
                "SELECT source_inventory_id, waiting_inventory_id, source_location, waiting_location, qty"
                " FROM export_waiting_items"
            ).fetchone()

    def test_repairs_item_whose_p_stock_was_quietly_moved_elsewhere(self):
        # P 재고행(id=1)은 이미 이동으로 비워졌고, 실제 200개는 일반 로케이션(B2-03-01)에 있다.
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO inventory VALUES(1,'노투스','오토 - DN MTS NEEDLE 12핀','오토 - DN MTS NEEDLE 12핀','-','-','P',0,'2026-09-01')"
            )
            con.execute(
                "INSERT INTO inventory VALUES(2,'노투스','오토 - DN MTS NEEDLE 12핀','오토 - DN MTS NEEDLE 12핀','-','-','B2-03-01',200,'2026-09-01')"
            )
            con.commit()
        self._seed()

        result = export_waiting.repair_broken_waiting_reservations("EXP-2026-024")

        self.assertEqual(result["failed"], [])
        self.assertEqual(len(result["repaired"]), 1)
        source_id, waiting_id, source_location, waiting_location, qty = self._item()
        self.assertEqual(waiting_location, "P")
        self.assertEqual(qty, 200)
        # B2-03-01의 200개가 다시 P로 재배치되어야 한다.
        rows = {row[1]: row[2] for row in self._inventory_rows()}
        self.assertEqual(rows.get("P"), 200)
        self.assertEqual(rows.get("B2-03-01", 0), 0)

    def test_healthy_reservation_is_left_untouched(self):
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO inventory VALUES(1,'노투스','오토 - DN MTS NEEDLE 12핀','오토 - DN MTS NEEDLE 12핀','-','-','P',200,'2026-09-01')"
            )
            con.commit()
        self._seed()

        result = export_waiting.repair_broken_waiting_reservations("EXP-2026-024")

        self.assertEqual(result, {"repaired": [], "failed": []})
        self.assertEqual(self._inventory_rows(), [(1, "P", 200)])

    def test_reports_failure_when_stock_is_truly_missing(self):
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO inventory VALUES(1,'노투스','오토 - DN MTS NEEDLE 12핀','오토 - DN MTS NEEDLE 12핀','-','-','P',0,'2026-09-01')"
            )
            con.commit()
        self._seed()

        result = export_waiting.repair_broken_waiting_reservations("EXP-2026-024")

        self.assertEqual(result["repaired"], [])
        self.assertEqual(len(result["failed"]), 1)
        # 손대지 않았어야 한다.
        source_id, waiting_id, source_location, waiting_location, qty = self._item()
        self.assertEqual(waiting_location, "P")


if __name__ == "__main__":
    unittest.main()
