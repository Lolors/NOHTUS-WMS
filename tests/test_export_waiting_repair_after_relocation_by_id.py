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


class RepairAfterRelocationByIdTests(unittest.TestCase):
    """예약 당시 기록된 원본 재고 id는 그대로 살아있는데, 그 사이 정상적인
    재고이동으로 물리적 위치만 바뀐 경우를 복구할 수 있어야 한다.

    실사용 버그: _source_identity_matches가 id 매칭 성공 조건에 "현재 위치가
    예약 당시 기록된 위치와 정확히 같아야 한다"는 조건을 덧붙이고 있어서,
    같은 id로 같은 재고임이 확실해도 위치가 바뀌었다는 이유만으로 "재고를
    찾을 수 없음"으로 오판했다. repair_broken_waiting_reservations는 바로
    이런 "재고이동으로 옮겨진 예약을 복구한다"는 목적의 함수인데, 그 목적
    자체를 무력화시키는 조건이었다."""

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

    def _seed(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO export_waiting_orders(export_no,country,buyer,transport_method,title,status,created_at,updated_at,created_by)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                ("EXP-2026-025", "USA", "미지정", "미지정", "테스트건", "waiting", now, now, "tester"),
            )
            order_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            # source_inventory_id=1은 예약 당시 T4에 있었다는 기록.
            con.execute(
                "INSERT INTO export_waiting_items(order_id,source_inventory_id,waiting_inventory_id,company,product_name,"
                "warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (order_id, 1, 1, "노투스", "볼덤 스폰지 트롤리", "볼덤 스폰지 트롤리",
                 "-", "-", "T4", "P", 1, now),
            )
            con.commit()
        return order_id

    def _item(self):
        with sqlite3.connect(self.db_path) as con:
            return con.execute(
                "SELECT source_inventory_id, waiting_inventory_id, source_location, waiting_location, qty"
                " FROM export_waiting_items"
            ).fetchone()

    def test_repairs_when_same_id_moved_to_a_different_real_location(self):
        # id=1은 여전히 같은 재고 row지만, 일반 재고이동으로 T4가 아니라
        # 지금은 A1에 있다 - id는 안 바뀌었으니 이걸로 바로 찾아야 한다.
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO inventory VALUES(1,'노투스','볼덤 스폰지 트롤리','볼덤 스폰지 트롤리','-','-','A1',1,'2026-09-01')"
            )
            con.commit()
        self._seed()

        result = export_waiting.repair_broken_waiting_reservations("EXP-2026-025")

        self.assertEqual(result["failed"], [])
        self.assertEqual(len(result["repaired"]), 1)
        _, _, _, waiting_location, qty = self._item()
        self.assertEqual(waiting_location, "P")
        self.assertEqual(qty, 1)
        with sqlite3.connect(self.db_path) as con:
            p_qty = con.execute("SELECT qty FROM inventory WHERE location='P'").fetchone()
        self.assertEqual(p_qty[0], 1)


if __name__ == "__main__":
    unittest.main()
