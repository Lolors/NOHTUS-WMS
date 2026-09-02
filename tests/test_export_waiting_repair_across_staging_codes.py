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


class RepairAcrossStagingCodesTests(unittest.TestCase):
    """P/T1~T5는 수출대기 보관 위치 코드이자 동시에 평범한 실물 선반 코드로도
    쓰인다. 예약은 P를 담당 보관 위치로 쓰는데, 실물은 재고이동 등록으로
    다른 보관위치 코드(T2)로 옮겨진 경우를 복구할 수 있어야 한다.

    실사용 버그: "실물 위치가 아닌 곳"만 찾는 재해석 검색이 보관위치 코드
    전체(P/T1~T5)를 무조건 배제해서, 재고가 분명히 재고현황에 있어도
    "실제 재고를 어디서도 찾지 못함"으로 계속 실패했다."""

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
                ("EXP-2026-030", "USA", "미지정", "미지정", "테스트건", "waiting", now, now, "tester"),
            )
            order_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            # source_inventory_id=99는 더 이상 존재하지 않는(예: 병합·소진된)
            # id라서 exact-id 매칭으로는 절대 못 찾는다 - 순수하게 재해석
            # 검색 경로만으로 복구되는지 확인한다.
            con.execute(
                "INSERT INTO export_waiting_items(order_id,source_inventory_id,waiting_inventory_id,company,product_name,"
                "warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (order_id, 99, 99, "노투스", "오메가 PDT 장비", "오메가 PDT 장비",
                 "-", "-", "T4", "P", 5, now),
            )
            con.commit()
        return order_id

    def _item(self):
        with sqlite3.connect(self.db_path) as con:
            return con.execute(
                "SELECT waiting_inventory_id, waiting_location, qty FROM export_waiting_items"
            ).fetchone()

    def test_repairs_when_stock_moved_to_a_different_staging_location_code(self):
        # P(자기 담당)에는 재고가 없고, 실물 5EA는 재고이동으로 T2(다른
        # 보관위치 코드)에 옮겨져 있다.
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO inventory VALUES(100,'노투스','오메가 PDT 장비','오메가 PDT 장비','-','-','T2',5,'2026-09-01')"
            )
            con.commit()
        self._seed()

        result = export_waiting.repair_broken_waiting_reservations("EXP-2026-030")

        self.assertEqual(result["failed"], [])
        self.assertEqual(len(result["repaired"]), 1)
        waiting_inventory_id, waiting_location, qty = self._item()
        self.assertEqual(waiting_location, "P")
        self.assertEqual(qty, 5)
        with sqlite3.connect(self.db_path) as con:
            p_qty = con.execute("SELECT qty FROM inventory WHERE location='P'").fetchone()[0]
            t2_qty = con.execute("SELECT qty FROM inventory WHERE location='T2'").fetchone()[0]
        self.assertEqual(p_qty, 5)
        self.assertEqual(t2_qty, 0)

    def test_repairs_when_quantity_is_split_between_own_location_and_another_staging_code(self):
        # 24EA 중 4EA는 이미 자기 담당 위치(P)에 정상적으로 있고, 나머지
        # 20EA는 재고이동으로 다른 보관위치 코드(T4)에 가 있다 - 사용자가
        # 보고한 "REC에서 P로, 나중에 다시 T4로 옮겼다"는 시나리오처럼 여러
        # 보관위치 코드에 걸쳐 나뉜 경우를 재현한다.
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO inventory VALUES(100,'노투스','오메가 PDT 장비','오메가 PDT 장비','-','-','P',4,'2026-09-01')"
            )
            con.execute(
                "INSERT INTO inventory VALUES(101,'노투스','오메가 PDT 장비','오메가 PDT 장비','-','-','T4',20,'2026-09-01')"
            )
            con.commit()
        order_id = self._seed()
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "UPDATE export_waiting_items SET qty=24,waiting_inventory_id=100 WHERE order_id=?",
                (order_id,),
            )
            con.commit()

        result = export_waiting.repair_broken_waiting_reservations("EXP-2026-030")

        self.assertEqual(result["failed"], [])
        self.assertEqual(len(result["repaired"]), 1)
        _, waiting_location, qty = self._item()
        self.assertEqual(waiting_location, "P")
        self.assertEqual(qty, 24)
        with sqlite3.connect(self.db_path) as con:
            p_qty = con.execute("SELECT qty FROM inventory WHERE location='P'").fetchone()[0]
            t4_qty = con.execute("SELECT qty FROM inventory WHERE location='T4'").fetchone()[0]
        # 기존에 P에 있던 4EA는 중복 가산 없이 그대로, T4의 20EA만 옮겨와서
        # 합계 24EA가 되어야 한다.
        self.assertEqual(p_qty, 24)
        self.assertEqual(t4_qty, 0)

    def test_does_not_steal_stock_already_reserved_by_another_order(self):
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO inventory VALUES(100,'노투스','오메가 PDT 장비','오메가 PDT 장비','-','-','T2',5,'2026-09-01')"
            )
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute(
                "INSERT INTO export_waiting_orders(export_no,country,buyer,transport_method,title,status,created_at,updated_at,created_by)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                ("EXP-OTHER", "USA", "미지정", "미지정", "다른건", "waiting", now, now, "tester"),
            )
            other_order_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            # 다른 주문이 이미 T2의 5EA 전량을 예약해 두었다.
            con.execute(
                "INSERT INTO export_waiting_items(order_id,source_inventory_id,waiting_inventory_id,company,product_name,"
                "warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (other_order_id, 100, 100, "노투스", "오메가 PDT 장비", "오메가 PDT 장비",
                 "-", "-", "T4", "T2", 5, now),
            )
            con.commit()
        self._seed()

        result = export_waiting.repair_broken_waiting_reservations("EXP-2026-030")

        self.assertEqual(result["repaired"], [])
        self.assertEqual(len(result["failed"]), 1)
        with sqlite3.connect(self.db_path) as con:
            t2_qty = con.execute("SELECT qty FROM inventory WHERE location='T2'").fetchone()[0]
        # 다른 주문의 예약 재고는 손대지 않았어야 한다.
        self.assertEqual(t2_qty, 5)


if __name__ == "__main__":
    unittest.main()
