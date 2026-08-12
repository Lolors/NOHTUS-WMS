import sqlite3
import unittest

from nohtus.db_init import _migrate_promo_rack_locations


class PromoRackMigrationTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        cur = self.con.cursor()
        cur.execute("CREATE TABLE inventory(id INTEGER PRIMARY KEY, location TEXT)")
        cur.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY, from_location TEXT, to_location TEXT)")
        cur.execute("CREATE TABLE outbound_order_items(id INTEGER PRIMARY KEY, inventory_id INTEGER, location TEXT)")
        cur.executemany(
            "INSERT INTO inventory(id, location) VALUES(?, ?)",
            [(1, "N-홍보물랙"), (2, "N - 홍보물랙"), (3, "N_홍보물랙"), (4, "A1-01")],
        )
        cur.execute("INSERT INTO transactions VALUES(1, 'N-홍보물랙', 'N - 홍보물랙')")
        cur.execute("INSERT INTO outbound_order_items VALUES(1, 1, 'N_홍보물랙')")

    def tearDown(self):
        self.con.close()

    def test_migrates_live_inventory_and_textual_references_without_changing_ids(self):
        cur = self.con.cursor()
        _migrate_promo_rack_locations(cur)

        self.assertEqual(
            cur.execute("SELECT id, location FROM inventory ORDER BY id").fetchall(),
            [(1, "홍보물랙"), (2, "홍보물랙"), (3, "홍보물랙"), (4, "A1-01")],
        )
        self.assertEqual(
            cur.execute("SELECT from_location, to_location FROM transactions").fetchone(),
            ("홍보물랙", "홍보물랙"),
        )
        self.assertEqual(
            cur.execute("SELECT inventory_id, location FROM outbound_order_items").fetchone(),
            (1, "홍보물랙"),
        )

    def test_migration_is_idempotent(self):
        cur = self.con.cursor()
        _migrate_promo_rack_locations(cur)
        first = self.con.total_changes
        _migrate_promo_rack_locations(cur)
        self.assertEqual(self.con.total_changes, first)


if __name__ == "__main__":
    unittest.main()
