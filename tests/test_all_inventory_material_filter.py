import sqlite3
import unittest

from nohtus.pages.all_inventory import _build_where


class AllInventoryMaterialFilterTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript(
            """
            CREATE TABLE products (standard_name TEXT, is_material);
            CREATE TABLE inventory (
                product_name TEXT, location TEXT, qty INTEGER,
                company TEXT, warehouse_name TEXT
            );
            """
        )

    def tearDown(self):
        self.con.close()

    def _visible_products(self, exclude_materials=True):
        where, params = _build_where([], "", "", exclude_materials=exclude_materials)
        rows = self.con.execute(
            f"SELECT product_name FROM inventory WHERE {where} ORDER BY product_name",
            params,
        ).fetchall()
        return [row[0] for row in rows]

    def test_master_flag_excludes_material_outside_material_location(self):
        self.con.execute("INSERT INTO products VALUES (?, ?)", ("체크된 부자재", 1))
        self.con.execute("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)",
                         ("체크된 부자재", "A1-01", 5, "NOH", "ERP"))

        self.assertEqual([], self._visible_products())
        self.assertEqual(["체크된 부자재"], self._visible_products(False))

    def test_legacy_true_representations_are_excluded_but_false_values_are_not(self):
        true_values = [1, "1", "true", "TRUE", "yes", "y", "o", "v", "체크", "부자재"]
        false_values = [None, 0, "0", "false", ""]
        for index, value in enumerate(true_values):
            name = f"material-{index}"
            self.con.execute("INSERT INTO products VALUES (?, ?)", (name, value))
            self.con.execute("INSERT INTO inventory VALUES (?, 'A1-01', 1, 'NOH', '')", (name,))
        for index, value in enumerate(false_values):
            name = f"normal-{index}"
            self.con.execute("INSERT INTO products VALUES (?, ?)", (name, value))
            self.con.execute("INSERT INTO inventory VALUES (?, 'A1-01', 1, 'NOH', '')", (name,))

        self.assertEqual([f"normal-{index}" for index in range(len(false_values))], self._visible_products())

    def test_any_matching_master_row_can_mark_product_as_material(self):
        self.con.executemany(
            "INSERT INTO products VALUES (?, ?)",
            [("중복 제품", 0), ("중복 제품", "true")],
        )
        self.con.execute("INSERT INTO inventory VALUES ('중복 제품', 'A1-01', 1, 'NOH', '')")

        self.assertEqual([], self._visible_products())


if __name__ == "__main__":
    unittest.main()
