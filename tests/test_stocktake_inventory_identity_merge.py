import sqlite3
import unittest

from nohtus.pages.stocktake_business import _update_inventory_identity


class StocktakeInventoryIdentityMergeTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute(
            """
            CREATE TABLE inventory(
                id INTEGER PRIMARY KEY,
                company TEXT,
                product_name TEXT,
                warehouse_name TEXT,
                lot TEXT,
                exp_date TEXT,
                location TEXT,
                qty INTEGER,
                updated_at TEXT
            )
            """
        )
        self.con.execute(
            """
            CREATE TABLE export_waiting_items(
                id INTEGER PRIMARY KEY,
                source_inventory_id INTEGER,
                waiting_inventory_id INTEGER
            )
            """
        )

    def tearDown(self):
        self.con.close()

    def test_same_location_merges_quantity_even_when_erp_names_differ(self):
        self.con.executemany(
            """
            INSERT INTO inventory(
                id, company, product_name, warehouse_name, lot,
                exp_date, location, qty
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            [
                (1, "NOH", "제품A", "기존 ERP명", "OLD", "2026-01-01", "A1", 3),
                (2, "NOH", "제품A", "다른 ERP명", "NEW", "2027-01-01", "A1", 7),
            ],
        )
        self.con.execute(
            "INSERT INTO export_waiting_items(id, source_inventory_id, waiting_inventory_id) VALUES(1,2,2)"
        )

        _update_inventory_identity(
            self.con, 1, "제품A", "NEW", "2027-01-01", "2026-08-18 10:00:00"
        )

        rows = self.con.execute(
            "SELECT id, warehouse_name, lot, exp_date, location, qty FROM inventory ORDER BY id"
        ).fetchall()
        links = self.con.execute(
            "SELECT source_inventory_id, waiting_inventory_id FROM export_waiting_items"
        ).fetchone()
        self.assertEqual(rows, [(1, "기존 ERP명", "NEW", "2027-01-01", "A1", 10)])
        self.assertEqual(links, (1, 1))

    def test_different_location_remains_a_separate_row(self):
        self.con.executemany(
            """
            INSERT INTO inventory(
                id, company, product_name, warehouse_name, lot,
                exp_date, location, qty
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            [
                (1, "NOH", "제품A", "ERP명", "OLD", "2026-01-01", "A1", 3),
                (2, "NOH", "제품A", "ERP명", "NEW", "2027-01-01", "B1", 7),
            ],
        )

        _update_inventory_identity(
            self.con, 1, "제품A", "NEW", "2027-01-01", "2026-08-18 10:00:00"
        )

        rows = self.con.execute(
            "SELECT id, lot, exp_date, location, qty FROM inventory ORDER BY id"
        ).fetchall()
        self.assertEqual(
            rows,
            [
                (1, "NEW", "2027-01-01", "A1", 3),
                (2, "NEW", "2027-01-01", "B1", 7),
            ],
        )


if __name__ == "__main__":
    unittest.main()
