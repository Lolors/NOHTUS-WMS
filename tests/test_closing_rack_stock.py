import json
import sqlite3
import unittest
from unittest.mock import patch

import pandas as pd
from nohtus.pages import closing


class ClosingRackStockTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute('''CREATE TABLE inventory (
            company TEXT, product_name TEXT, lot TEXT, exp_date TEXT,
            location TEXT, location_range_cells TEXT, location_range_end TEXT, qty INTEGER)''')
        self.query_patch = patch.object(closing, 'q', side_effect=lambda sql, params=(): pd.read_sql_query(sql, self.conn, params=params))
        self.query = self.query_patch.start()

    def tearDown(self):
        self.query_patch.stop()
        self.conn.close()

    def add(self, location, qty, *, cells=None, end=None, company='노투스팜', product='제품A', lot='LOT1', exp='2028-01-01'):
        self.conn.execute('INSERT INTO inventory VALUES (?,?,?,?,?,?,?,?)', (company, product, lot, exp, location, json.dumps(cells) if cells else None, end, qty))

    def items(self, *locations):
        return pd.DataFrame([{'사업장':'노투스팜','로케이션':loc,'표준제품명':'제품A','제조번호':'LOT1','유통기한':'2028-01-01','출고수량':2,'매출처':'거래처'} for loc in locations])

    def totals(self, *locations):
        return list(closing._location_final_stock_map(self.items(*locations)).values())

    def test_whole_rack_and_next_rack_are_separate(self):
        self.add('A1-01-01', 10)
        self.add('A1-02-02', 20)
        self.add('A1-03-03', 30)
        self.add('A1-04-01', 100)
        self.assertEqual(self.totals('A1-01-01','A1-03-02','A1-04-01'), [60,60,100])
        self.assertEqual(self.query.call_count, 1)

    def test_range_rows_count_once_and_legacy_range_is_included(self):
        self.add('A1-01-01', 50, cells=['A1-01-01','A1-02-02','A1-03-03','A1-03-03'])
        self.add('A1-02-01', 15, end='A1-03-03')
        self.assertEqual(self.totals('A1-03-02'), [65])

    def test_range_overlap_uses_occupied_cells_not_only_anchor(self):
        self.add('A1-04-01', 7, cells=['A1-03-01','A1-04-01'])
        self.assertEqual(self.totals('A1-01-01'), [7])

    def test_stock_identity_and_other_locations_stay_separate(self):
        self.add('A1-02-01', 5)
        self.add('A1-02-01', 100, company='NOH')
        self.add('A1-02-01', 100, product='제품B')
        self.add('A1-02-01', 100, lot='LOT2')
        self.add('A1-02-01', 100, exp='2029-01-01')
        self.add('B1-02-01', 100)
        self.add('P', 100)
        self.assertEqual(self.totals('A1-01-01'), [5])

    def test_special_locations_remain_exact(self):
        self.add('P', 9)
        self.add('T1', 12)
        self.add('A1-01-01', 50)
        self.assertEqual(self.totals('P','T1','T2'), [9,12,0])

    def test_reversed_rack_and_four_level_rack(self):
        self.add('A1-10-01', 10)
        self.add('A1-12-03', 12)
        self.add('A1-13-01', 100)
        self.add('X1-03-04', 4)
        self.assertEqual(self.totals('A1-11-02','X1-01-01'), [22,4])

    def test_table_and_print_share_same_totals(self):
        self.add('A1-02-03', 17)
        rows=self.items('A1-01-01','A1-01-01')
        self.assertEqual(closing._today_outbound_display_df(rows)['최종재고'].tolist(), [17,''])
        for include_style in [True,False]:
            html=closing._today_outbound_html(rows,include_style=include_style)
            self.assertIn("<td class='num' rowspan='2'>17</td>", html)
        self.assertEqual(closing._location_final_stock_map(pd.DataFrame()), {})


if __name__ == '__main__':
    unittest.main()
