from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from nohtus.export_app import db
from nohtus.export_app.services import order_service
from nohtus.services import export_waiting as export_waiting_service
from nohtus.export_app.utils.dates import now_text


class SaveOrderItemsReconcilesOrphanWaitingItemsTests(unittest.TestCase):
    """주문목록을 저장할 때마다(제품이 바뀌든, 수량만 바뀌든) 더 이상 어떤
    저장분(shipment_items)도 필요로 하지 않는 WMS 수출대기(P) 예약을 자동으로
    정리한다.

    실사용 버그: 어떤 수출건의 주문목록에서 제품이 빠진 뒤에도, 그 제품
    때문에 P로 옮겨졌던 재고 예약이 export_waiting_items에 그대로 남아
    다른 수출건에서 영원히 고를 수 없는 상태가 됐다. 이 정리는 예전에
    "주문 검색 및 수정" 화면을 다시 열어야만(그리고 그 case가 아직
    활성 상태일 때만) 돌았는데, 이미 패킹 완료된 건은 그 화면을 다시 열
    일이 없어 고아 예약이 영구히 남았다."""

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()

        self.original_db_path = db.DB_PATH
        self.original_upload_dir = db.UPLOAD_DIR
        db.DB_PATH = Path(self.temp_dir.name) / 'export.db'
        db.UPLOAD_DIR = Path(self.temp_dir.name) / 'uploads'
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        self.backup_patch = patch.object(db, 'backup_to_usb', return_value=None)
        self.backup_patch.start()
        db.init_db()

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        self._closing_connection = ClosingConnection

        self.wms_db_path = Path(self.temp_dir.name) / 'wms.db'
        with sqlite3.connect(self.wms_db_path, factory=ClosingConnection) as con:
            con.execute(
                '''CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT, product_name TEXT,
                       warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT,
                       qty INTEGER, updated_at TEXT, is_shippable INTEGER
                   )'''
            )
            con.execute(
                '''CREATE TABLE transactions(
                       id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, actor TEXT,
                       tx_type TEXT, product_name TEXT, warehouse_name TEXT, lot TEXT,
                       exp_date TEXT, from_company TEXT, from_location TEXT,
                       to_company TEXT, to_location TEXT, qty INTEGER, memo TEXT,
                       final_stock INTEGER
                   )'''
            )
            export_waiting_service.ensure_export_waiting_tables(con.cursor())
            con.commit()
        self.wms_connect_patcher = patch(
            'nohtus.export_app.services.stale_inventory_cleanup_service.wms_connect',
            lambda: sqlite3.connect(self.wms_db_path, factory=ClosingConnection),
        )
        self.wms_connect_patcher.start()

    def tearDown(self) -> None:
        self.wms_connect_patcher.stop()
        self.backup_patch.stop()
        db.DB_PATH = self.original_db_path
        db.UPLOAD_DIR = self.original_upload_dir
        db._initialize_database_runtime.cache_clear()
        db.init_db.cache_clear()
        self.temp_dir.cleanup()

    def test_saving_order_list_frees_orphaned_p_reservation(self) -> None:
        now = now_text()
        case_id = db.execute(
            '''INSERT INTO export_cases(
                   export_no,country,stage,status,created_at,updated_at,case_type
               ) VALUES (?,?,?,?,?,?,?)''',
            ('EXP-ORPHAN-1', 'KR', '패킹 완료', '진행중', now, now, 'current'),
        )
        order_id = db.execute(
            '''INSERT INTO order_items(case_id,product_name,quantity,unit,created_at)
               VALUES (?,?,?,?,?)''',
            (case_id, '몰딩클리어', 2, 'BOX', now),
        )

        # WMS 쪽: "루나 아이즈"가 예전에 이 수출건 주문목록에 있었을 때 P로
        # 옮겨졌지만, 지금 case의 shipment_items/order_items 어디에도
        # 흔적이 없는 고아 예약.
        with sqlite3.connect(self.wms_db_path, factory=self._closing_connection) as con:
            wms_now = now_text()
            cur = con.execute(
                '''INSERT INTO export_waiting_orders(
                       export_no,country,buyer,transport_method,title,status,created_at,updated_at
                   ) VALUES (?,?,?,?,?,?,?,?)''',
                ('EXP-ORPHAN-1', 'KR', 'Buyer', '항공', 'KR-Buyer-항공', 'waiting', wms_now, wms_now),
            )
            wms_order_id = int(cur.lastrowid)
            con.execute(
                '''INSERT INTO inventory(company,product_name,warehouse_name,lot,exp_date,location,qty,updated_at,is_shippable)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                ('노투스팜', '루나 아이즈 2ml*1s', '', 'LIBCJL523010', '2029-07-08', 'P', 15, wms_now, 0),
            )
            p_inventory_id = int(con.execute('SELECT last_insert_rowid()').fetchone()[0])
            con.execute(
                '''INSERT INTO export_waiting_items(
                       order_id,source_inventory_id,waiting_inventory_id,company,product_name,
                       warehouse_name,lot,exp_date,source_location,waiting_location,qty,moved_at,confirmed
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    wms_order_id, p_inventory_id, p_inventory_id, '노투스팜', '루나 아이즈 2ml*1s',
                    '', 'LIBCJL523010', '2029-07-08', 'B1-06-02', 'P', 15, wms_now, 0,
                ),
            )
            con.commit()

        # 주문목록을 저장한다(이 케이스에서는 기존 행 수량만 바뀔 뿐이고,
        # "루나 아이즈"는 애초에 order_items/shipment_items 어디에도 없다 -
        # 실사용 버그를 그대로 재현한다: 정리가 이 저장 시점에 자동으로
        # 같이 일어나야 한다).
        edited = pd.DataFrame([
            {'_id': order_id, '제품명': '몰딩클리어', '수량': 3.0, '단위': 'BOX', '매입가': 0.0, '1단위당 EA': 1.0},
        ])
        order_service.save_order_items(case_id, edited)

        with sqlite3.connect(self.wms_db_path, factory=self._closing_connection) as con:
            remaining = con.execute(
                'SELECT qty FROM export_waiting_items WHERE order_id=? AND product_name=?',
                (wms_order_id, '루나 아이즈 2ml*1s'),
            ).fetchone()
            p_qty = con.execute(
                'SELECT qty FROM inventory WHERE id=?', (p_inventory_id,)
            ).fetchone()[0]

        self.assertIsNone(remaining, '고아 예약이 정리되지 않고 그대로 남았습니다.')
        self.assertEqual(p_qty, 0, 'P 재고 수량이 정리 후에도 그대로입니다.')


if __name__ == '__main__':
    unittest.main()
