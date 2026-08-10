import sqlite3

from nohtus.services import export_waiting


def _connect_to(path):
    return lambda: sqlite3.connect(path)


def _create_tables(con):
    con.executescript(
        """
        CREATE TABLE inventory(
            id INTEGER PRIMARY KEY, company TEXT, product_name TEXT,
            warehouse_name TEXT, lot TEXT, exp_date TEXT, location TEXT, qty INTEGER
        );
        CREATE TABLE export_waiting_items(
            id INTEGER PRIMARY KEY, order_id INTEGER, waiting_inventory_id INTEGER,
            company TEXT, product_name TEXT, warehouse_name TEXT, lot TEXT,
            exp_date TEXT, qty INTEGER, confirmed INTEGER DEFAULT 0
        );
        """
    )


def test_repairs_dangling_p_inventory_id_with_exact_inventory_key(tmp_path, monkeypatch):
    database = tmp_path / "test.db"
    with sqlite3.connect(database) as con:
        _create_tables(con)
        con.execute(
            "INSERT INTO inventory VALUES(20,'휴온스','휴온스피리독신염산염주사액 50A','ERP명','LOT1','2027-01-01','P',50)"
        )
        con.execute(
            "INSERT INTO export_waiting_items VALUES(1,7,999,'휴온스','휴온스피리독신염산염주사액 50A','ERP명','LOT1','2027-01-01',10,0)"
        )
    monkeypatch.setattr(export_waiting, "connect", _connect_to(database))

    assert export_waiting.repair_p_inventory_links(7) == 1

    with sqlite3.connect(database) as con:
        assert con.execute(
            "SELECT waiting_inventory_id FROM export_waiting_items WHERE id=1"
        ).fetchone()[0] == 20


def test_does_not_guess_when_multiple_exact_p_rows_exist(tmp_path, monkeypatch):
    database = tmp_path / "test.db"
    with sqlite3.connect(database) as con:
        _create_tables(con)
        con.executemany(
            "INSERT INTO inventory VALUES(?,?,?,?,?,?,?,?)",
            [
                (20, '휴온스', '제품A', 'ERP명', 'LOT1', '2027-01-01', 'P', 50),
                (21, '휴온스', '제품A', 'ERP명', 'LOT1', '2027-01-01', 'P', 50),
            ],
        )
        con.execute(
            "INSERT INTO export_waiting_items VALUES(1,7,999,'휴온스','제품A','ERP명','LOT1','2027-01-01',10,0)"
        )
    monkeypatch.setattr(export_waiting, "connect", _connect_to(database))

    assert export_waiting.repair_p_inventory_links(7) == 0

    with sqlite3.connect(database) as con:
        assert con.execute(
            "SELECT waiting_inventory_id FROM export_waiting_items WHERE id=1"
        ).fetchone()[0] == 999
