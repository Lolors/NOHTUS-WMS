import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.pages import history


class HistoryLogOnlyDeleteResyncsLastSalesTests(unittest.TestCase):
    """'이력만 삭제(원복 없음)' 경로도 '삭제+재고 원복' 경로와 똑같이
    customer_last_sales를 재동기화해야 한다(과거엔 이 경로만 재동기화를
    안 탔다). 이미 취소된 주문의 이력 로그만 정리하는 경우처럼, 남아있는
    유효한 주문 기준으로 '최근거래'를 다시 계산해줘야 하는 상황을 검증한다."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "history.db"
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY, tx_type TEXT, memo TEXT, from_company TEXT)")
            con.execute(
                "CREATE TABLE outbound_orders(id INTEGER PRIMARY KEY, order_date TEXT, title TEXT, "
                "customer_name TEXT, customer_company TEXT, status TEXT)"
            )
            con.execute(
                "CREATE TABLE customer_last_sales(id INTEGER PRIMARY KEY, customer_name TEXT, company TEXT, "
                "last_sale_date TEXT, updated_at TEXT)"
            )
            con.execute(
                "INSERT INTO transactions VALUES(1,'출고','출고지시서 #2 배송','노투스')"
            )
            con.executemany(
                "INSERT INTO outbound_orders VALUES(?,?,?,?,?,?)",
                [
                    (1, "2026-01-05", "1차 출고", "ABC", "노투스", "완료"),
                    # 2번 주문은 이미 다른 경로로 취소된 상태인데, 그 이력만
                    # 아직 지워지지 않고 남아 있었다고 가정한다.
                    (2, "2026-01-10", "2차 출고", "ABC", "노투스", "취소됨"),
                ],
            )
            con.execute(
                "INSERT INTO customer_last_sales VALUES(1,'ABC','노투스','2026-01-10','2026-01-10 00:00:00')"
            )
            con.commit()
        finally:
            con.close()

        class ClosingConnection(sqlite3.Connection):
            def __exit__(self, exc_type, exc_value, traceback):
                try:
                    return super().__exit__(exc_type, exc_value, traceback)
                finally:
                    self.close()

        def connect_test_db():
            return sqlite3.connect(self.db_path, factory=ClosingConnection)

        self.connect_patcher = patch.object(history, "connect", connect_test_db)
        self.connect_patcher.start()

    def tearDown(self):
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def test_log_only_delete_recomputes_last_sale_date(self):
        deleted_orders = history._deleted_outbound_orders_for_transactions([1])
        deleted = history._delete_transaction_ids_without_reversal([1])
        history._sync_customer_last_sales_after_delete(deleted_orders)

        con = sqlite3.connect(self.db_path)
        try:
            last_sale_date = con.execute(
                "SELECT last_sale_date FROM customer_last_sales WHERE customer_name='ABC' AND company='노투스'"
            ).fetchone()[0]
            transactions_left = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        finally:
            con.close()

        self.assertEqual(deleted, 1)
        self.assertEqual(transactions_left, 0)
        # 2번 주문(2026-01-10)은 이미 취소된 상태라 유효 주문에서 제외되고,
        # 남은 유효 주문 중 가장 최근인 2026-01-05로 다시 계산돼야 한다.
        self.assertEqual(last_sale_date, "2026-01-05")


if __name__ == "__main__":
    unittest.main()
