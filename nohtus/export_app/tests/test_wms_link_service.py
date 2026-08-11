from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import nohtus.services.export_waiting as export_waiting_service
from nohtus.export_app import db
from nohtus.export_app.services import shipment_service, wms_link_service
from nohtus.export_app.utils.dates import now_text


class WmsLinkServiceTests(unittest.TestCase):
    """실출고 입력의 실재고 피커는 저장할 때마다 nohtus.services.export_waiting.
    save_export_waiting_order()를 부르는데, 이 함수는 editing_order_id로 기존
    건을 수정할 때 그 건의 미확정 품목 '전체'를 넘긴 cart로 통째로 교체한다
    (부분 추가가 아니다). wms_link_service.save_picked_inventory()가 매번 이
    케이스의 다른 주문품목에 이미 연결된 실재고까지 함께 담아 보내지 않으면,
    나중에 연결한 주문품목이 먼저 연결해둔 주문품목의 실재고 연결을 조용히
    원위치로 복원시켜 버린다. 이 파일은 그 사고가 나지 않는지 확인한다."""

    def setUp(self) -> None:
        self.wms_temp_dir = tempfile.TemporaryDirectory()
        self.wms_db_path = Path(self.wms_temp_dir.name) / "wms.db"

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        def connect_wms_test_db():
            return sqlite3.connect(self.wms_db_path, factory=ClosingConnection)

        self.wms_connect_patchers = [
            patch("nohtus.db.connect", connect_wms_test_db),
            patch("nohtus.services.export_waiting.connect", connect_wms_test_db),
        ]
        for patcher in self.wms_connect_patchers:
            patcher.start()

        with sqlite3.connect(self.wms_db_path, factory=ClosingConnection) as con:
            con.execute(
                """CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY,location TEXT,company TEXT,product_name TEXT,
                       warehouse_name TEXT,lot TEXT,exp_date TEXT,qty INTEGER,updated_at TEXT
                   )"""
            )
            con.execute(
                """CREATE TABLE transactions(
                       id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT,actor TEXT,tx_type TEXT,
                       product_name TEXT,warehouse_name TEXT,lot TEXT,exp_date TEXT,from_company TEXT,
                       from_location TEXT,to_company TEXT,to_location TEXT,qty INTEGER,memo TEXT,
                       final_stock INTEGER
                   )"""
            )
            con.executemany(
                """INSERT INTO inventory(id,location,company,product_name,warehouse_name,lot,exp_date,qty,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                [
                    (1, "A1-01", "NOH", "제품A", "ERP-A", "LOT-1", "2027-01-01", 20, "2026-01-01"),
                    (2, "A1-02", "NOH", "제품B", "ERP-B", "LOT-2", "2027-02-01", 15, "2026-01-01"),
                ],
            )

        export_waiting_service.ensure_export_waiting_tables()

        self.export_temp_dir = TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        self.original_upload_dir = db.UPLOAD_DIR
        db.DB_PATH = Path(self.export_temp_dir.name) / "export.db"
        db.UPLOAD_DIR = Path(self.export_temp_dir.name) / "uploads"
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        self.usb_backup_patch = patch.object(db, "backup_to_usb", return_value=None)
        self.usb_backup_patch.start()
        db.init_db()

    def tearDown(self) -> None:
        self.usb_backup_patch.stop()
        db.DB_PATH = self.original_db_path
        db.UPLOAD_DIR = self.original_upload_dir
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        self.export_temp_dir.cleanup()

        for patcher in self.wms_connect_patchers:
            patcher.stop()
        self.wms_temp_dir.cleanup()

    def _create_case(self, export_no: str) -> tuple[int, int, int]:
        now = now_text()
        case_id = db.execute(
            '''INSERT INTO export_cases(export_no,country,buyer,transport_mode,stage,status,created_at,updated_at,case_type)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (export_no, "KR", "테스트바이어", "AIR", "주문 접수", "진행중", now, now, "current"),
        )
        order_a = db.execute(
            '''INSERT INTO order_items(case_id,product_name,quantity,unit,created_at) VALUES (?,?,?,?,?)''',
            (case_id, "제품A-주문용", 5, "EA", now),
        )
        order_b = db.execute(
            '''INSERT INTO order_items(case_id,product_name,quantity,unit,created_at) VALUES (?,?,?,?,?)''',
            (case_id, "제품B-주문용", 3, "EA", now),
        )
        return case_id, order_a, order_b

    def _wms_inventory_row(self, product_name: str) -> dict:
        con = sqlite3.connect(self.wms_db_path)
        try:
            con.row_factory = sqlite3.Row
            row = con.execute(
                "SELECT * FROM inventory WHERE product_name=? AND location<>'P'", (product_name,)
            ).fetchone()
            return dict(row) if row else {}
        finally:
            con.close()

    def _wms_p_qty(self, product_name: str) -> int:
        con = sqlite3.connect(self.wms_db_path)
        try:
            row = con.execute(
                "SELECT COALESCE(SUM(qty),0) FROM inventory WHERE product_name=? AND location='P'",
                (product_name,),
            ).fetchone()
            return int(row[0] or 0)
        finally:
            con.close()

    def _wms_export_waiting_items(self) -> list[dict]:
        con = sqlite3.connect(self.wms_db_path)
        try:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute("SELECT * FROM export_waiting_items ORDER BY id").fetchall()]
        finally:
            con.close()

    def test_second_order_item_link_does_not_wipe_first(self) -> None:
        case_id, order_a, order_b = self._create_case("EXP-LINK-001")

        result_a = wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_a,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 1,
                "company": "NOH",
                "product_name": "제품A",
                "lot": "LOT-1",
                "exp_date": "2027-01-01",
                "location": "A1-01",
                "qty": 5.0,
            }],
        )
        self.assertEqual(result_a["row_count"], 1)

        rows_a = shipment_service.list_case_items(case_id)
        linked_a = [r for r in rows_a if r["order_item_id"] == order_a]
        self.assertEqual(len(linked_a), 1)
        self.assertEqual(linked_a[0]["product_name"], "제품A")
        self.assertEqual(float(linked_a[0]["requested_qty"]), 5.0)
        self.assertIsNotNone(linked_a[0]["source_inventory_id"])

        self.assertEqual(self._wms_inventory_row("제품A")["qty"], 15)
        self.assertEqual(self._wms_p_qty("제품A"), 5)

        # 두 번째 주문품목(제품B)에 실재고를 연결한다. save_export_waiting_order가
        # editing_order_id로 같은 WMS 건을 수정하면서, 먼저 연결해둔 제품A의
        # 연결까지 통째로 복원시켜 버리지 않는지가 이 테스트의 핵심이다.
        result_b = wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_b,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 2,
                "company": "NOH",
                "product_name": "제품B",
                "lot": "LOT-2",
                "exp_date": "2027-02-01",
                "location": "A1-02",
                "qty": 3.0,
            }],
        )
        self.assertEqual(result_a["order_id"], result_b["order_id"])

        rows_after = shipment_service.list_case_items(case_id)
        linked_a_after = [r for r in rows_after if r["order_item_id"] == order_a]
        linked_b_after = [r for r in rows_after if r["order_item_id"] == order_b]

        self.assertEqual(len(linked_a_after), 1, "제품A에 연결한 실재고가 사라지면 안 된다")
        self.assertEqual(float(linked_a_after[0]["requested_qty"]), 5.0)
        self.assertEqual(len(linked_b_after), 1)
        self.assertEqual(float(linked_b_after[0]["requested_qty"]), 3.0)

        # WMS 쪽 실재고도 두 품목 모두 P 로케이션에 그대로 있어야 하고,
        # 제품A가 원위치로 복원되었다가 다시 이동한 흔적(수량 중복 등)이 없어야 한다.
        self.assertEqual(self._wms_p_qty("제품A"), 5)
        self.assertEqual(self._wms_p_qty("제품B"), 3)
        self.assertEqual(self._wms_inventory_row("제품A")["qty"], 15)
        self.assertEqual(self._wms_inventory_row("제품B")["qty"], 12)

        export_items = self._wms_export_waiting_items()
        self.assertEqual(len(export_items), 2)
        self.assertEqual({item["product_name"] for item in export_items}, {"제품A", "제품B"})

    def test_restores_preintegration_p_stock_links_without_moving_inventory_again(self) -> None:
        case_id, order_a, _ = self._create_case("EXP-LEGACY-001")
        result = wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_a,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 1,
                "company": "NOH",
                "product_name": "제품A",
                "lot": "LOT-1",
                "exp_date": "2027-01-01",
                "location": "A1-01",
                "qty": 5.0,
            }],
        )
        self.assertEqual(result["row_count"], 1)
        db.execute("DELETE FROM shipment_items WHERE case_id=?", (case_id,))
        # 통합 전/DB 정리 과정에서 P 재고 id 연결이 끊어진 상태도 자동 복구한다.
        with sqlite3.connect(self.wms_db_path) as con:
            con.execute(
                "UPDATE export_waiting_items SET waiting_inventory_id=999 WHERE order_id=?",
                (int(result["order_id"]),),
            )

        restored = wms_link_service.restore_legacy_waiting_links(case_id)
        self.assertEqual(restored, 1)
        linked = shipment_service.list_case_items(case_id)
        self.assertEqual(len(linked), 1)
        self.assertEqual(int(linked[0]["order_item_id"]), order_a)
        self.assertEqual(float(linked[0]["requested_qty"]), 5.0)
        self.assertEqual(self._wms_p_qty("제품A"), 5)
        self.assertEqual(self._wms_inventory_row("제품A")["qty"], 15)

        self.assertEqual(wms_link_service.restore_legacy_waiting_links(case_id), 0)
        self.assertEqual(len(shipment_service.list_case_items(case_id)), 1)

    def test_reuses_matching_legacy_export_row_instead_of_doubling_received_qty(self) -> None:
        case_id, order_a, _ = self._create_case("EXP-LEGACY-EXISTING")
        result = wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_a,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 1,
                "company": "NOH",
                "product_name": "제품A",
                "lot": "LOT-1",
                "exp_date": "2027-01-01",
                "location": "A1-01",
                "qty": 5.0,
            }],
        )
        db.execute("DELETE FROM shipment_items WHERE case_id=?", (case_id,))
        now = now_text()
        legacy_id = db.execute(
            """INSERT INTO shipment_items(
                   case_id,order_item_id,business_unit,location,source_inventory_id,
                   product_name,lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (case_id, order_a, "NOH", "", None, "제품A (5 EA)", "LOT-1",
             "2027-1-1", 5, 7, now, now),
        )

        restored = wms_link_service.restore_legacy_waiting_links(case_id)

        self.assertEqual(restored, 1)
        linked = shipment_service.list_case_items(case_id)
        self.assertEqual(len(linked), 1)
        self.assertEqual(int(linked[0]["id"]), legacy_id)
        self.assertEqual(int(linked[0]["source_inventory_id"]), 1)
        self.assertEqual(linked[0]["source_location"], "A1-01")
        self.assertEqual(linked[0]["product_name"], "제품A")
        self.assertEqual(linked[0]["lot_no"], "LOT-1")
        self.assertEqual(linked[0]["expiry_date"], "2027-01-01")
        self.assertEqual(float(linked[0]["requested_qty"]), 5.0)
        self.assertEqual(int(linked[0]["box_no"]), 7)
        self.assertEqual(wms_link_service.restore_legacy_waiting_links(case_id), 0)

    def test_removes_duplicate_restore_row_and_preserves_packed_legacy_row(self) -> None:
        case_id, order_a, _ = self._create_case("EXP-LEGACY-DOUBLED")
        wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_a,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 1,
                "company": "NOH",
                "product_name": "제품A",
                "lot": "LOT-1",
                "exp_date": "2027-01-01",
                "location": "A1-01",
                "qty": 5.0,
            }],
        )
        now = now_text()
        legacy_id = db.execute(
            """INSERT INTO shipment_items(
                   case_id,order_item_id,business_unit,location,source_inventory_id,
                   product_name,lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (case_id, order_a, "NOH", "", None, "제품A", "LOT-1",
             "2027-01-01", 5, 3, now, now),
        )
        self.assertEqual(shipment_service.total_linked_quantity(case_id), 10.0)

        restored = wms_link_service.restore_legacy_waiting_links(case_id)

        self.assertEqual(restored, 1)
        linked = shipment_service.list_case_items(case_id)
        self.assertEqual(len(linked), 1)
        self.assertEqual(int(linked[0]["id"]), legacy_id)
        self.assertEqual(int(linked[0]["source_inventory_id"]), 1)
        self.assertEqual(float(linked[0]["requested_qty"]), 5.0)
        self.assertEqual(int(linked[0]["box_no"]), 3)
        self.assertEqual(shipment_service.total_linked_quantity(case_id), 5.0)
        self.assertEqual(wms_link_service.restore_legacy_waiting_links(case_id), 0)

    def test_links_split_ctn_rows_when_their_group_total_matches_p_inventory(self) -> None:
        case_id, order_a, _ = self._create_case("EXP-LEGACY-SPLIT")
        wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_a,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 1,
                "company": "NOH",
                "product_name": "제품A",
                "lot": "LOT-1",
                "exp_date": "2027-01-01",
                "location": "A1-01",
                "qty": 5.0,
            }],
        )
        db.execute("DELETE FROM shipment_items WHERE case_id=?", (case_id,))
        now = now_text()
        for quantity, box_no in ((2, 1), (3, 2)):
            db.execute(
                """INSERT INTO shipment_items(
                       case_id,order_item_id,business_unit,location,source_inventory_id,
                       product_name,lot_no,expiry_date,requested_qty,box_no,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (case_id, order_a, "NOH", "", None, "제품A", "LOT-1",
                 "2027-01-01", quantity, box_no, now, now),
            )

        self.assertEqual(wms_link_service.restore_legacy_waiting_links(case_id), 1)

        linked = shipment_service.list_case_items(case_id)
        self.assertEqual(len(linked), 2)
        self.assertEqual({int(row["source_inventory_id"]) for row in linked}, {1})
        self.assertEqual({int(row["box_no"]) for row in linked}, {1, 2})
        self.assertEqual(sum(float(row["requested_qty"]) for row in linked), 5.0)
        self.assertEqual(wms_link_service.restore_legacy_waiting_links(case_id), 0)

    def test_restores_confirmed_wms_items_as_received_without_p_stock(self) -> None:
        case_id, order_a, _ = self._create_case("EXP-CONFIRMED-LEGACY")
        result = wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_a,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 1,
                "company": "NOH",
                "product_name": "제품A",
                "lot": "LOT-1",
                "exp_date": "2027-01-01",
                "location": "A1-01",
                "qty": 5.0,
            }],
        )
        db.execute("DELETE FROM shipment_items WHERE case_id=?", (case_id,))
        with sqlite3.connect(self.wms_db_path) as con:
            waiting_inventory_id = con.execute(
                "SELECT waiting_inventory_id FROM export_waiting_items WHERE order_id=?",
                (int(result["order_id"]),),
            ).fetchone()[0]
            con.execute("DELETE FROM inventory WHERE id=?", (waiting_inventory_id,))
            con.execute(
                "UPDATE export_waiting_items SET confirmed=1 WHERE order_id=?",
                (int(result["order_id"]),),
            )
            con.execute(
                "UPDATE export_waiting_orders SET status='confirmed' WHERE id=?",
                (int(result["order_id"]),),
            )

        restored = wms_link_service.restore_legacy_waiting_links(case_id)

        self.assertEqual(restored, 1)
        linked = shipment_service.list_case_items(case_id)
        self.assertEqual(len(linked), 1)
        self.assertEqual(int(linked[0]["order_item_id"]), order_a)
        self.assertEqual(float(linked[0]["requested_qty"]), 5.0)
        self.assertEqual(wms_link_service.restore_legacy_waiting_links(case_id), 0)

    def test_removing_a_kept_row_restores_wms_inventory(self) -> None:
        # save_export_waiting_order()는 건 전체의 품목이 0개가 되는 저장은 거부하므로
        # (수출대기 자체를 취소하는 것과는 다른 조작), 다른 주문품목에 실재고가 하나
        # 더 연결되어 있는 상태에서 이번 주문품목의 연결만 전부 지우는 시나리오로 검증한다.
        case_id, order_a, order_b = self._create_case("EXP-LINK-002")

        wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_a,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 1,
                "company": "NOH",
                "product_name": "제품A",
                "lot": "LOT-1",
                "exp_date": "2027-01-01",
                "location": "A1-01",
                "qty": 5.0,
            }],
        )
        wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_b,
            kept_rows=[],
            picked_rows=[{
                "inventory_id": 2,
                "company": "NOH",
                "product_name": "제품B",
                "lot": "LOT-2",
                "exp_date": "2027-02-01",
                "location": "A1-02",
                "qty": 3.0,
            }],
        )
        self.assertEqual(self._wms_p_qty("제품A"), 5)
        self.assertEqual(self._wms_p_qty("제품B"), 3)

        # order_a의 kept_rows를 비워서 다시 저장하면(= UI에서 기존 연결을 삭제
        # 표시한 뒤 저장), 그 실재고는 P에서 원래 위치로 복원되어야 하고
        # order_b의 연결은 그대로 남아 있어야 한다.
        wms_link_service.save_picked_inventory(
            case_id=case_id,
            order_item_id=order_a,
            kept_rows=[],
            picked_rows=[],
        )

        self.assertEqual(self._wms_p_qty("제품A"), 0)
        self.assertEqual(self._wms_inventory_row("제품A")["qty"], 20)
        self.assertEqual(self._wms_p_qty("제품B"), 3)

        rows_after = shipment_service.list_case_items(case_id)
        self.assertEqual([r for r in rows_after if r["order_item_id"] == order_a], [])
        linked_b_after = [r for r in rows_after if r["order_item_id"] == order_b]
        self.assertEqual(len(linked_b_after), 1)
        self.assertEqual(float(linked_b_after[0]["requested_qty"]), 3.0)


if __name__ == "__main__":
    unittest.main()
