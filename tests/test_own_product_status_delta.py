import sqlite3
import unittest
from unittest.mock import patch
import pandas as pd
from nohtus.pages import own_product_status as page


class OwnProductDeltaTests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:')
        self.conn.execute('CREATE TABLE transactions(created_at TEXT,tx_type TEXT,product_name TEXT,from_company TEXT,to_company TEXT,qty INTEGER)')
        self.conn.execute('CREATE TABLE inventory(company TEXT,product_name TEXT,qty INTEGER)')
        self.patches=[patch.object(page,'_today_text',return_value='2026-10-01'),patch.object(page,'q',side_effect=lambda sql,params=():pd.read_sql_query(sql,self.conn,params=params))]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in self.patches:p.stop()
        self.conn.close()

    def tx(self, kind, qty, source='노투스팜', target=None, day='2026-10-01'):
        self.conn.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?)',(day+' 09:00:00',kind,'델가다 (5EA)',source,target,qty))

    def delta(self,company='노투스팜'):
        return page._today_delta_map()[(company,'델가다 (5EA)')]

    def test_sixty_cancelled_leaves_thirty_and_correct_previous_stock(self):
        self.tx('출고지시',60);self.tx('출고지시',30);self.tx('출고지시취소',60)
        self.assertEqual(self.delta(),-30)
        self.conn.execute('INSERT INTO inventory VALUES (?,?,?)',('노투스팜','델가다 (5EA)',283))
        row=page._company_table('노투스팜',page._today_delta_map(),{}).set_index('표준제품명').loc['델가다 (5EA)']
        self.assertEqual((row['전일수량'],row['증감'],row['현재수량']),('313','-30','283'))

    def test_quantity_decrease_increase_then_full_cancel_nets_zero(self):
        self.tx('출고지시',60);self.tx('출고지시 재차감',-20)
        self.assertEqual(self.delta(),-40)
        self.tx('출고지시 재차감',10)
        self.assertEqual(self.delta(),-50)
        self.tx('출고지시취소',50,target='노투스팜')
        self.assertEqual(self.delta(),0)

    def test_replacement_company_restores_old_and_deducts_new(self):
        self.tx('출고지시',60);self.tx('출고지시취소',60)
        self.tx('출고지시',60,source='NOH')
        self.assertEqual(self.delta(),0)
        self.assertEqual(self.delta('NOH'),-60)

    def test_explicit_restore_destination_takes_precedence(self):
        self.tx('출고지시취소',9,source='NOH',target='노투스팜')
        self.assertEqual(self.delta(),9)
        self.assertEqual(self.delta('NOH'),0)

    def test_prior_day_excluded_and_same_company_move_does_not_change_delta(self):
        self.tx('출고지시',60,day='2026-09-30')
        self.tx('출고지시취소',60)
        self.tx('위치이동',110,target='노투스팜')
        self.tx('사업장이동',20,target='노투스팜')
        self.assertEqual(self.delta(),60)

    def test_inbound_and_intercompany_transfer_unchanged(self):
        self.tx('입고',100,source=None,target='노투스팜')
        self.tx('사업장이동',30,target='NOH')
        self.assertEqual(self.delta(),70)
        self.assertEqual(self.delta('NOH'),30)


if __name__=='__main__':unittest.main()
