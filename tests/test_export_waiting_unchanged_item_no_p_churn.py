import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.export_waiting import (
    ensure_export_waiting_tables,
    save_export_waiting_order,
)


class ExportWaitingUnchangedItemNoPChurnTests(unittest.TestCase):
    """수출대기 저장을 다시 눌러도 수량이 그대로인 품목은 P<->원위치를
    왕복시키지 않는다.

    실사용 버그: P 재고 연결(waiting_inventory_id)이 끊어져 있으면(재고조사,
    다른 위치이동 등으로 흔히 발생) 매 저장마다 불필요하게 복원→재적재를
    반복하던 기존 로직이 "이미 원위치에 있다"는 조용한 폴백을 반복 발동시켜,
    실제로는 P로 옮겨진 적 없는 것처럼 원래 위치(예: T4)에 재고가 눌러앉는
    사고로 이어졌다. 수량이 안 바뀐 품목은 애초에 손대지 않으면 이 문제가
    발생하지 않는다.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "unchanged.db"

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        self.connection_factory = ClosingConnection

        def connect_test_db():
            return sqlite3.connect(self.db_path, factory=ClosingConnection)

        self.connect_patcher = patch("nohtus.services.export_waiting.connect", connect_test_db)
        self.connect_patcher.start()
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            con.execute(
                """CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY,location TEXT,company TEXT,product_name TEXT,
                       warehouse_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER,
                       updated_at TEXT,is_shippable INTEGER
                   )"""
            )
            con.execute(
                """CREATE TABLE transactions(
                       id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, actor TEXT, tx_type TEXT,
                       product_name TEXT, warehouse_name TEXT, lot TEXT, exp_date TEXT,
                       from_company TEXT, from_location TEXT, to_company TEXT, to_location TEXT,
                       qty INTEGER, memo TEXT, final_stock INTEGER
                   )"""
            )
        ensure_export_waiting_tables()

    def tearDown(self):
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def _connect(self):
        return sqlite3.connect(self.db_path, factory=self.connection_factory)

    def test_adding_a_new_item_does_not_disturb_an_unrelated_unchanged_item(self):
        with self._connect() as con:
            # T4에서 P로 이미 10EA가 정상적으로 옮겨진 기존 품목. T4 원본 행은
            # 이미 다 소진되어 0EA만 남아 있다(정상 흐름).
            con.execute(
                "INSERT INTO inventory VALUES(10,'T4','NOH','볼덤 스폰지 트롤리','','LOT1','2027-01-01',0,'2026-01-01',1)"
            )
            # P쪽 실재고가 일부만(6EA) 남아 있다 - 재고조사/다른 주문의 부분
            # 확정 출고 등으로 흔히 생기는, 기록된 예약수량(10)보다 실제 P
            # 재고가 적은 상태를 재현한다.
            con.execute(
                "INSERT INTO inventory VALUES(20,'P','NOH','볼덤 스폰지 트롤리','','LOT1','2027-01-01',6,'2026-01-01',0)"
            )
            # 새로 담을 다른 제품의 원본 재고(아직 수출대기에 없음).
            con.execute(
                "INSERT INTO inventory VALUES(30,'T5','NOH','다른제품','','LOT2','2027-06-01',5,'2026-01-01',1)"
            )
            cur = con.execute(
                """INSERT INTO export_waiting_orders(
                       export_no,country,buyer,transport_method,title,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                ("EXP-1", "KR", "Buyer", "항공", "KR-Buyer-항공", "waiting", "2026-01-01", "2026-01-01"),
            )
            order_id = int(cur.lastrowid)
            con.execute(
                """INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,waiting_inventory_id,company,product_name,warehouse_name,
                       lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_id, 10, 20, "NOH", "볼덤 스폰지 트롤리", "", "LOT1", "2027-01-01", "T4", "P", 10, "2026-01-01", 0),
            )

        # 기존 품목(id=10, 수량 10)은 그대로 두고, 새 품목(id=30)만 추가해서
        # 저장한다 - 실제 "수출대기 저장" 화면에서 새로 고른 재고를 담아
        # 저장 버튼을 누르는 것과 같다.
        cart = [
            {
                "id": 10, "요청수량": 10, "사업장": "NOH", "제품명": "볼덤 스폰지 트롤리",
                "LOT": "LOT1", "유통기한": "2027-01-01", "로케이션": "T4",
            },
            {
                "id": 30, "요청수량": 5, "사업장": "NOH", "제품명": "다른제품",
                "LOT": "LOT2", "유통기한": "2027-06-01", "로케이션": "T5",
            },
        ]

        result = save_export_waiting_order(
            cart, country="KR", buyer="Buyer", transport_method="항공",
            export_no="EXP-1", editing_order_id=order_id,
        )
        self.assertEqual(result["order_id"], order_id)

        with self._connect() as con:
            rows = con.execute(
                "SELECT source_inventory_id,waiting_inventory_id,source_location,waiting_location,qty "
                "FROM export_waiting_items WHERE order_id=? ORDER BY source_inventory_id",
                (order_id,),
            ).fetchall()
            # 기존 품목(10)은 원래 연결(waiting_inventory_id=20) 그대로 남고,
            # 새 품목(30)만 추가된다 - 기존 품목을 위해 P<->원위치를 왕복시키지
            # 않았으므로 P쪽의 부족한 실재고(6EA)로 인한 오류도 발생하지 않는다.
            self.assertEqual(len(rows), 2)
            existing_row = next(r for r in rows if r[0] == 10)
            new_row = next(r for r in rows if r[0] == 30)
            self.assertEqual(existing_row, (10, 20, "T4", "P", 10))
            self.assertEqual((new_row[0], new_row[2], new_row[3], new_row[4]), (30, "T5", "P", 5))
            self.assertIsNotNone(new_row[1])
            t4_qty = con.execute("SELECT qty FROM inventory WHERE id=10").fetchone()[0]
            p20_qty = con.execute("SELECT qty FROM inventory WHERE id=20").fetchone()[0]
            t5_qty = con.execute("SELECT qty FROM inventory WHERE id=30").fetchone()[0]
            self.assertEqual(t4_qty, 0)
            self.assertEqual(p20_qty, 6)
            self.assertEqual(t5_qty, 0)


if __name__ == "__main__":
    unittest.main()
