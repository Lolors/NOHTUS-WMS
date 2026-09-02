from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from nohtus.export_app.services import wms_link_edit_patch


class FillSourceLinksMultipleSameSignatureRowsTests(unittest.TestCase):
    """같은 사업장/제품명/LOT/유통기한을 가진 재고가 여러 행으로 나뉘어
    있어도, 그 행들은 전부 같은 재고이므로 자동 연결이 가능해야 한다.

    실사용 버그: SQL where절이 이미 사업장/제품명/LOT/유통기한까지 정확히
    일치하는 후보만 걸렀는데도, _fill_source_links가 "후보가 정확히 1개일
    때만" 연결을 허용해서, 같은 재고가 재고이동/조정 등으로 두 행으로
    나뉜(예: 40EA 두 번 입고돼서 40+40) 경우 "이미 같은 재고임이 확실한데도"
    자동 연결을 포기해버렸다. 그 결과 "수출대기 저장에는 있지만 수출확정
    목록에서 자동으로 연결하지 못한 품목"으로 영원히 남았다."""

    def setUp(self) -> None:
        self._tmpdir = TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmpdir.name) / 'wms.db'
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                '''CREATE TABLE inventory(
                       id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT, product_name TEXT,
                       warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT,
                       qty INTEGER, updated_at TEXT
                   )'''
            )
            con.execute(
                '''CREATE TABLE export_waiting_items(
                       id INTEGER PRIMARY KEY, order_id INTEGER, waiting_inventory_id INTEGER,
                       qty INTEGER, confirmed INTEGER DEFAULT 0
                   )'''
            )
            con.execute(
                '''CREATE TABLE export_waiting_orders(
                       id INTEGER PRIMARY KEY, status TEXT
                   )'''
            )
            con.commit()
        self._connect_patcher = patch.object(
            wms_link_edit_patch, 'connect', lambda: sqlite3.connect(self.db_path)
        )

        def _wms_q(sql, params=()):
            with sqlite3.connect(self.db_path) as con:
                return pd.read_sql_query(sql, con, params=params)

        self._wms_q_patcher = patch.object(wms_link_edit_patch, 'wms_q', _wms_q)
        self._connect_patcher.start()
        self._wms_q_patcher.start()

    def tearDown(self) -> None:
        self._wms_q_patcher.stop()
        self._connect_patcher.stop()
        self._tmpdir.cleanup()

    def test_resolves_when_the_same_stock_key_is_split_across_two_inventory_rows(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO inventory VALUES(10,'노투스팜','바이리쥬 2ml','바이리쥬 2ml','BR250402','2028-04-01','P',40,'2026-09-01')"
            )
            con.execute(
                "INSERT INTO inventory VALUES(11,'노투스팜','바이리쥬 2ml','바이리쥬 2ml','BR250402','2028-04-01','P',40,'2026-09-01')"
            )
            con.commit()

        rows = [
            {
                'business_unit': '노투스팜', 'product_name': '바이리쥬 2ml',
                'lot_no': 'BR250402', 'expiry_date': '2028-04-01',
                'requested_qty': 40, 'source_inventory_id': None, 'source_location': '',
            },
            {
                'business_unit': '노투스팜', 'product_name': '바이리쥬 2ml',
                'lot_no': 'BR250402', 'expiry_date': '2028-04-01',
                'requested_qty': 40, 'source_inventory_id': None, 'source_location': '',
            },
        ]

        wms_link_edit_patch._fill_source_links(rows, waiting_rows=[])

        for row in rows:
            self.assertIsNotNone(row['source_inventory_id'])
            self.assertIn(row['source_inventory_id'], (10, 11))


if __name__ == '__main__':
    unittest.main()
