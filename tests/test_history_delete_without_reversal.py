import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nohtus.pages import history


class HistoryDeleteWithoutReversalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'history.db'
        con = sqlite3.connect(self.db_path)
        try:
            con.execute('CREATE TABLE inventory(id INTEGER PRIMARY KEY, qty INTEGER)')
            con.execute('CREATE TABLE transactions(id INTEGER PRIMARY KEY, memo TEXT)')
            con.execute('INSERT INTO inventory VALUES(1, 17)')
            con.executemany('INSERT INTO transactions VALUES(?,?)', [(1, '오류 점검'), (2, '유지할 이력')])
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

        self.connect_patcher = patch.object(history, 'connect', connect_test_db)
        self.connect_patcher.start()

    def tearDown(self):
        self.connect_patcher.stop()
        self.temp_dir.cleanup()

    def test_deletes_only_log_rows_without_inventory_change_or_new_log(self):
        deleted = history._delete_transaction_ids_without_reversal([1, 999])

        con = sqlite3.connect(self.db_path)
        try:
            inventory_qty = con.execute('SELECT qty FROM inventory WHERE id=1').fetchone()[0]
            transactions = con.execute('SELECT id,memo FROM transactions ORDER BY id').fetchall()
        finally:
            con.close()

        self.assertEqual(deleted, 1)
        self.assertEqual(inventory_qty, 17)
        self.assertEqual(transactions, [(2, '유지할 이력')])


if __name__ == '__main__':
    unittest.main()
