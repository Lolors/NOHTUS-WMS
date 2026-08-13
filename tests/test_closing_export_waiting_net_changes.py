import sqlite3
import unittest
from unittest.mock import patch

import pandas as pd

from nohtus.pages.closing_export_history_patch import _patched_export_waiting_rows


class ClosingExportWaitingNetChangeTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(':memory:')
        self.con.execute('''CREATE TABLE export_waiting_orders(
            id INTEGER PRIMARY KEY, export_no TEXT, title TEXT, status TEXT, created_at TEXT
        )''')
        self.con.execute('''CREATE TABLE export_waiting_items(
            id INTEGER PRIMARY KEY, order_id INTEGER, source_inventory_id INTEGER,
            company TEXT, source_location TEXT, product_name TEXT, lot TEXT,
            exp_date TEXT, qty INTEGER
        )''')
        self.con.execute('''CREATE TABLE transactions(
            id INTEGER PRIMARY KEY, created_at TEXT, tx_type TEXT, memo TEXT,
            from_company TEXT, to_company TEXT, from_location TEXT, to_location TEXT,
            product_name TEXT, lot TEXT, exp_date TEXT, qty INTEGER
        )''')
        self.con.execute(
            "INSERT INTO export_waiting_orders VALUES(1,'EXP-1','필리핀-바이어-해상','waiting','2026-08-01')"
        )

    def tearDown(self):
        self.con.close()

    def _movement(self, product, from_location, to_location, qty=160):
        self.con.execute(
            '''INSERT INTO transactions(
                created_at,tx_type,memo,from_company,to_company,from_location,to_location,
                product_name,lot,exp_date,qty
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (
                '2026-08-13 10:00:00', '위치이동',
                '수출대기 수정 / 기존 목록 / 수출번호: EXP-1',
                '노투스팜', '노투스팜', from_location, to_location,
                product, 'LOT-1', '2029-05-28', qty,
            ),
        )

    def _query(self, sql, params=()):
        return pd.read_sql_query(sql, self.con, params=params)

    def test_repeated_restore_and_reload_does_not_inflate_every_order_item(self):
        for _ in range(8):
            for product in ('제품A', '제품B'):
                self._movement(product, 'P', 'B1-03-02')
                self._movement(product, 'B1-03-02', 'P')
        self.con.commit()

        with patch(
            'nohtus.pages.closing_export_history_patch.ensure_export_waiting_tables'
        ):
            result = _patched_export_waiting_rows(self._query, '2026-08-13')

        self.assertTrue(result.empty)

    def test_only_real_net_increase_is_shown(self):
        self._movement('제품A', 'P', 'B1-03-02', 160)
        self._movement('제품A', 'B1-03-02', 'P', 160)
        self._movement('제품A', 'B1-03-02', 'P', 5)
        self.con.commit()

        with patch(
            'nohtus.pages.closing_export_history_patch.ensure_export_waiting_tables'
        ):
            result = _patched_export_waiting_rows(self._query, '2026-08-13')

        self.assertEqual(result['표준제품명'].tolist(), ['제품A'])
        self.assertEqual(result['출고수량'].tolist(), [5])


if __name__ == '__main__':
    unittest.main()
