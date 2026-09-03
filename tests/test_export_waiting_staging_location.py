import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.services.export_waiting import (
    ensure_export_waiting_tables,
    save_export_waiting_order,
    cancel_export_waiting_order,
    confirm_export_waiting_items,
)


class ExportWaitingStagingLocationTests(unittest.TestCase):
    """수출대기 재고는 기본적으로 P에 쌓이지만, P가 가득 찼거나 별도 보관이
    필요하면 T1~T5 중 아무 위치나 골라서 대신 쌓을 수 있어야 한다."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "staging.db"

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
        with sqlite3.connect(self.db_path, factory=ClosingConnection) as con:
            con.execute(
                """CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY,location TEXT,company TEXT,product_name TEXT,
                       warehouse_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER,
                       updated_at TEXT,is_shippable INTEGER
                   )"""
            )
            con.execute(
                """CREATE TABLE transactions(
                       id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT,actor TEXT,tx_type TEXT,
                       product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,
                       from_company TEXT,from_location TEXT,to_company TEXT,to_location TEXT,
                       qty INTEGER,memo TEXT,final_stock INTEGER
                   )"""
            )
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(1,'A1','NOH','제품','ERP-A','LOT-1','2027-01-01',10,'2026-01-01',1)"""
            )
        ensure_export_waiting_tables()

    def tearDown(self):
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def _cart(self, qty=4):
        return [{
            "id": 1, "사업장": "NOH", "제품명": "제품", "warehouse_name": "ERP-A",
            "LOT": "LOT-1", "유통기한": "2027-01-01", "로케이션": "A1", "요청수량": qty,
        }]

    def test_new_order_stages_stock_at_chosen_t_location_instead_of_p(self):
        result = save_export_waiting_order(
            self._cart(), country="KR", export_no="EXP-1", staging_location="T3",
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            item = con.execute(
                "SELECT source_location,waiting_location,qty FROM export_waiting_items WHERE order_id=?",
                (result["order_id"],),
            ).fetchone()
            source_qty = con.execute("SELECT qty FROM inventory WHERE id=1").fetchone()[0]
            t3_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T3'").fetchone()[0]
            p_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='P'").fetchone()[0]

        self.assertEqual(item, ("A1", "T3", 4))
        self.assertEqual(source_qty, 6)
        self.assertEqual(t3_qty, 4)
        self.assertEqual(p_qty, 0)

    def test_rejects_unknown_staging_location(self):
        with self.assertRaisesRegex(ValueError, "P, T1~T5"):
            save_export_waiting_order(
                self._cart(), country="KR", export_no="EXP-1", staging_location="Z9",
            )

    def test_cancel_restores_stock_from_t_location_back_to_source(self):
        result = save_export_waiting_order(
            self._cart(), country="KR", export_no="EXP-1", staging_location="T4",
        )

        cancel_export_waiting_order(result["order_id"])

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            source_qty = con.execute("SELECT qty FROM inventory WHERE id=1").fetchone()[0]
            t4_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T4'").fetchone()[0]
            status = con.execute(
                "SELECT status FROM export_waiting_orders WHERE id=?", (result["order_id"],)
            ).fetchone()[0]

        self.assertEqual(source_qty, 10)
        self.assertEqual(t4_qty, 0)
        self.assertEqual(status, "cancelled")

    def test_confirm_consumes_stock_from_its_own_t_location_not_p(self):
        result = save_export_waiting_order(
            self._cart(), country="KR", export_no="EXP-1", staging_location="T5",
        )
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            item_id = con.execute(
                "SELECT id FROM export_waiting_items WHERE order_id=?", (result["order_id"],)
            ).fetchone()[0]

        confirm_export_waiting_items(
            result["order_id"], [item_id],
            erp_company="NOH", customer_code="C1", customer_name="수출처",
            shipment_date="2026-03-01",
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            t5_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T5'").fetchone()[0]
            confirmed = con.execute(
                "SELECT confirmed FROM export_waiting_items WHERE id=?", (item_id,)
            ).fetchone()[0]

        self.assertEqual(t5_qty, 0)
        self.assertEqual(confirmed, 1)

    def test_unrelated_resave_ignores_healthy_item_even_if_its_recorded_source_location_collides_with_staging(self):
        """일부 품목은 원래 T1~T5 같은 '기타 위치' 랙이 정식 보관장소라, 그
        위치 그대로 export_waiting_items.source_location에 'T5'처럼 수출대기
        보관 위치 코드와 우연히 같은 값이 남을 수 있다. 이 품목이 여전히
        멀쩡하게 연결되어 있고 수량도 그대로라면, 그 품목과 무관한 다른
        품목만 수정해 저장해도 절대 다시 손대면 안 된다 — 예전에는 저장할
        때마다 미확정 품목 전체를 원위치로 되돌렸다가 다시 담았는데, 이
        'T5' 값이 수출대기 위치 코드와 겹치는 바람에 재고를 다시 찾다가
        "재고를 찾을 수 없습니다/재고가 부족합니다" 오류로 무관한 저장까지
        막는 사고로 이어졌다."""
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(101,'REC','NOH','거치대','거치대','-','-',1,'2026-01-01',1)"""
            )
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(102,'A1','NOH','니들','니들','-','-',200,'2026-01-01',1)"""
            )
        item1 = {
            "id": 101, "사업장": "NOH", "제품명": "거치대", "warehouse_name": "거치대",
            "LOT": "-", "유통기한": "-", "로케이션": "REC", "요청수량": 1,
        }
        item2 = {
            "id": 102, "사업장": "NOH", "제품명": "니들", "warehouse_name": "니들",
            "LOT": "-", "유통기한": "-", "로케이션": "A1", "요청수량": 10,
        }
        result = save_export_waiting_order([item1, item2], country="KR", export_no="EXP-1")

        # 실제 데이터에서는 '거치대'류 품목이 애초에 T1~T5 랙에 있다가 그대로
        # 예약된 경우 source_location에 'T5'가 남는다. P 대기 재고 자체는
        # 멀쩡한 채로 이 값만 그렇게 겹치는 상황을 재현한다.
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            con.execute(
                "UPDATE export_waiting_items SET source_location='T5' WHERE product_name='거치대'"
            )
            con.commit()

        item2_more = dict(item2, 요청수량=20)
        save_export_waiting_order(
            [item1, item2_more],
            country="KR", export_no="EXP-1", editing_order_id=result["order_id"],
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            qty_by_product = dict(con.execute(
                "SELECT product_name,qty FROM export_waiting_items WHERE order_id=?",
                (result["order_id"],),
            ).fetchall())
            gochidae_waiting_id = con.execute(
                "SELECT waiting_inventory_id FROM export_waiting_items WHERE product_name='거치대'"
            ).fetchone()[0]

        self.assertEqual(qty_by_product["거치대"], 1)
        self.assertEqual(qty_by_product["니들"], 20)
        # 손대지 않았으니 대기 재고 연결(id)도 그대로여야 한다.
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            waiting_qty = con.execute(
                "SELECT qty FROM inventory WHERE id=?", (gochidae_waiting_id,)
            ).fetchone()[0]
        self.assertEqual(waiting_qty, 1)

    def test_unrelated_resave_does_not_relocate_existing_staged_item(self):
        """T3에 이미 쌓아둔 재고가 있는 주문을, 다른 이유로 (기본 P인 채로)
        다시 저장해도 기존 품목은 T3에 그대로 남아야 한다 — target_location은
        새로 담기는 품목에만 적용된다."""
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(2,'B1','NOH','제품B','ERP-B','LOT-2','2028-01-01',10,'2026-01-01',1)"""
            )
        result = save_export_waiting_order(
            self._cart(qty=4), country="KR", export_no="EXP-1", staging_location="T3",
        )

        save_export_waiting_order(
            [
                self._cart(qty=4)[0],
                {
                    "id": 2, "사업장": "NOH", "제품명": "제품B", "warehouse_name": "ERP-B",
                    "LOT": "LOT-2", "유통기한": "2028-01-01", "로케이션": "B1", "요청수량": 3,
                },
            ],
            country="KR", export_no="EXP-1", editing_order_id=result["order_id"],
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            locations = dict(con.execute(
                "SELECT source_inventory_id,waiting_location FROM export_waiting_items WHERE order_id=?",
                (result["order_id"],),
            ).fetchall())
            t3_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T3'").fetchone()[0]
            p_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='P'").fetchone()[0]

        self.assertEqual(locations, {1: "T3", 2: "P"})
        self.assertEqual(t3_qty, 4)
        self.assertEqual(p_qty, 3)

    def test_waiting_location_reflects_where_stock_actually_already_sits(self):
        """실사용 버그: 재고가 이미 T4처럼 다른 수출대기 위치 코드에 있으면
        _take_source가 "이미 대기 위치에 있다"고 보고 실제로는 옮기지 않는데,
        그런데도 waiting_location 컬럼에는 물리적으로 옮기지 않은 target
        위치(P)가 그대로 기록됐다. 그 결과 export_waiting_items는 'P에
        있다'고 주장하지만 실제 재고는 T4에 남아있어, 이후 자동 복구
        로직이 "재고를 찾을 수 없다"고 오판하는 사고로 이어졌다."""
        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            con.execute(
                """INSERT INTO inventory(
                       id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at,is_shippable
                   ) VALUES(3,'T4','NOH','제품C','ERP-C','-','-',200,'2026-01-01',1)"""
            )
        result = save_export_waiting_order(
            [{
                "id": 3, "사업장": "NOH", "제품명": "제품C", "warehouse_name": "ERP-C",
                "LOT": "-", "유통기한": "-", "로케이션": "T4", "요청수량": 200,
            }],
            country="KR", export_no="EXP-1",
        )

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            waiting_location = con.execute(
                "SELECT waiting_location FROM export_waiting_items WHERE order_id=?",
                (result["order_id"],),
            ).fetchone()[0]
            t4_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='T4'").fetchone()[0]
            p_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='P'").fetchone()[0]

        self.assertEqual(waiting_location, "T4")
        self.assertEqual(t4_qty, 200)
        self.assertEqual(p_qty, 0)

    def test_default_staging_location_is_still_p(self):
        result = save_export_waiting_order(self._cart(), country="KR", export_no="EXP-1")

        with sqlite3.connect(self.db_path, factory=self.connection_factory) as con:
            waiting_location = con.execute(
                "SELECT waiting_location FROM export_waiting_items WHERE order_id=?",
                (result["order_id"],),
            ).fetchone()[0]
            p_qty = con.execute("SELECT COALESCE(SUM(qty),0) FROM inventory WHERE location='P'").fetchone()[0]

        self.assertEqual(waiting_location, "P")
        self.assertEqual(p_qty, 4)


if __name__ == "__main__":
    unittest.main()
