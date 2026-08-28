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
            [(1, "다용도랙"), (2, "다용도랙"), (3, "다용도랙"), (4, "A1-01")],
        )
        self.assertEqual(
            cur.execute("SELECT from_location, to_location FROM transactions").fetchone(),
            ("다용도랙", "다용도랙"),
        )
        self.assertEqual(
            cur.execute("SELECT inventory_id, location FROM outbound_order_items").fetchone(),
            (1, "다용도랙"),
        )

    def test_migration_is_idempotent(self):
        cur = self.con.cursor()
        _migrate_promo_rack_locations(cur)
        first = self.con.total_changes
        _migrate_promo_rack_locations(cur)
        self.assertEqual(self.con.total_changes, first)

    def test_bare_legacy_spelling_also_migrates(self):
        cur = self.con.cursor()
        cur.execute("INSERT INTO inventory(id, location) VALUES(5, '홍보물랙')")
        _migrate_promo_rack_locations(cur)

        self.assertEqual(
            cur.execute("SELECT location FROM inventory WHERE id=5").fetchone(),
            ("다용도랙",),
        )

    def test_conflicting_inventory_row_is_skipped_without_raising(self):
        cur = self.con.cursor()
        cur.execute(
            "CREATE UNIQUE INDEX ux_inventory_logical_key ON inventory(location)"
        )
        cur.execute("INSERT INTO inventory(id, location) VALUES(6, '다용도랙')")
        # id=1 normalizes to the same '다용도랙' location and would collide with
        # id=6 under the unique index above; the migration must not crash.
        _migrate_promo_rack_locations(cur)


if __name__ == "__main__":
    unittest.main()
