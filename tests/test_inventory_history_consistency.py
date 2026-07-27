import sqlite3
import unittest

from nohtus.services.inventory import assert_stock_key_history_consistent


class InventoryHistoryConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.cur = self.con.cursor()
        self.cur.execute(
            """CREATE TABLE inventory(
                   id INTEGER PRIMARY KEY,
                   company TEXT,
                   product_name TEXT,
                   lot TEXT,
                   exp_date TEXT,
                   location TEXT,
                   qty INTEGER
               )"""
        )
        self.cur.execute(
            """CREATE TABLE transactions(
                   id INTEGER PRIMARY KEY,
                   tx_type TEXT,
                   product_name TEXT,
                   lot TEXT,
                   exp_date TEXT,
                   from_company TEXT,
                   to_company TEXT,
                   final_stock INTEGER
               )"""
        )

    def tearDown(self):
        self.con.close()

    def _inventory(self, qty):
        self.cur.execute(
            """INSERT INTO inventory(company,product_name,lot,exp_date,location,qty)
               VALUES('노투스','제품 A','AR0425001','2028-04-20','T2',?)""",
            (qty,),
        )

    def _history(self, final_stock, tx_type="출고지시", from_company="노투스", to_company=None):
        self.cur.execute(
            """INSERT INTO transactions(
                   tx_type,product_name,lot,exp_date,from_company,to_company,final_stock
               ) VALUES(?,?,?,?,?,?,?)""",
            (tx_type, "제품 A", "AR0425001", "2028-04-20", from_company, to_company, final_stock),
        )

    def _assert_consistent(self):
        assert_stock_key_history_consistent(
            self.cur,
            company="노투스",
            product_name="제품 A",
            lot="AR0425001",
            exp_date="2028-04-20",
        )

    def test_matching_current_stock_and_latest_history_pass(self):
        self._inventory(584)
        self._history(584)

        self._assert_consistent()

    def test_silent_restore_is_blocked_before_outbound_edit(self):
        self._inventory(601)
        self._history(584)

        with self.assertRaisesRegex(ValueError, r"현재고\(601EA\).*최근 이력 최종재고\(584EA\)"):
            self._assert_consistent()

        actual = self.cur.execute("SELECT qty FROM inventory").fetchone()[0]
        self.assertEqual(actual, 601)

    def test_legitimate_later_history_allows_updated_current_stock(self):
        self._inventory(601)
        self._history(584)
        self._history(601, tx_type="입고", from_company=None, to_company="노투스")

        self._assert_consistent()

    def test_other_company_history_is_ignored(self):
        self._inventory(584)
        self._history(999, from_company="NOH")
        self._history(584)

        self._assert_consistent()


if __name__ == "__main__":
    unittest.main()
