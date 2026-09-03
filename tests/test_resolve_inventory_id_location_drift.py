import sqlite3
import unittest

from nohtus.services.outbound_orders import _resolve_inventory_id


class ResolveInventoryIdLocationDriftTests(unittest.TestCase):
    """저장된 출고지시서의 재고행이 그 사이 다른 칸으로 이동했어도(예: 재고
    이동 등록), 사업장/제품/LOT/유통기한이 같으면 여전히 같은 재고 배치로
    보고 찾아내야 한다 — 로케이션 문자열이 달라졌다는 이유만으로 "출고지시를
    수정할 수 없습니다" 오류가 나면 안 된다."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute(
            """
            CREATE TABLE inventory(
                id INTEGER PRIMARY KEY, product_name TEXT, company TEXT, location TEXT,
                lot TEXT, exp_date TEXT, warehouse_name TEXT, qty INTEGER
            )
            """
        )

    def tearDown(self):
        self.con.close()

    def test_finds_row_after_location_moved(self):
        cur = self.con.cursor()
        cur.execute(
            "INSERT INTO inventory VALUES(1,'콘쥬란 (5 Syringe)','노투스팜','B1-10-01','25001A','2028-11-26','콘쥬란 (5 Syringe)',100)"
        )
        item = {
            '제품명': '콘쥬란 (5 Syringe)', '사업장': '노투스팜',
            '로케이션': 'B1-12-02', 'LOT': '25001A', '유통기한': '2028-11-26',
        }
        self.assertEqual(_resolve_inventory_id(cur, item), 1)

    def test_still_matches_when_row_now_has_zero_qty(self):
        cur = self.con.cursor()
        cur.execute(
            "INSERT INTO inventory VALUES(1,'콘쥬란 (5 Syringe)','노투스팜','B1-10-01','25001A','2028-11-26','콘쥬란 (5 Syringe)',0)"
        )
        item = {
            '제품명': '콘쥬란 (5 Syringe)', '사업장': '노투스팜',
            '로케이션': 'B1-12-02', 'LOT': '25001A', '유통기한': '2028-11-26',
        }
        self.assertEqual(_resolve_inventory_id(cur, item), 1)

    def test_does_not_match_different_lot_even_at_same_old_location(self):
        cur = self.con.cursor()
        cur.execute(
            "INSERT INTO inventory VALUES(1,'콘쥬란 (5 Syringe)','노투스팜','B1-12-02','99999Z','2099-01-01','콘쥬란 (5 Syringe)',5)"
        )
        item = {
            '제품명': '콘쥬란 (5 Syringe)', '사업장': '노투스팜',
            '로케이션': 'B1-12-02', 'LOT': '25001A', '유통기한': '2028-11-26',
        }
        self.assertIsNone(_resolve_inventory_id(cur, item))

    def test_returns_none_when_product_missing_entirely(self):
        cur = self.con.cursor()
        item = {
            '제품명': '없는 제품', '사업장': '노투스팜',
            '로케이션': 'B1-12-02', 'LOT': '25001A', '유통기한': '2028-11-26',
        }
        self.assertIsNone(_resolve_inventory_id(cur, item))

    def test_prefers_exact_location_match_over_moved_row(self):
        cur = self.con.cursor()
        cur.execute(
            "INSERT INTO inventory VALUES(1,'콘쥬란 (5 Syringe)','노투스팜','B1-10-01','25001A','2028-11-26','콘쥬란 (5 Syringe)',100)"
        )
        cur.execute(
            "INSERT INTO inventory VALUES(2,'콘쥬란 (5 Syringe)','노투스팜','B1-12-02','25001A','2028-11-26','콘쥬란 (5 Syringe)',5)"
        )
        item = {
            '제품명': '콘쥬란 (5 Syringe)', '사업장': '노투스팜',
            '로케이션': 'B1-12-02', 'LOT': '25001A', '유통기한': '2028-11-26',
        }
        self.assertEqual(_resolve_inventory_id(cur, item), 2)


if __name__ == '__main__':
    unittest.main()
