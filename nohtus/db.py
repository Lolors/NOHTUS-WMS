import sqlite3

import pandas as pd

from .config import DB_PATH


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def q(sql, params=()):
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params)


def exec_sql(sql, params=()):
    with connect() as con:
        con.execute(sql, params)
        con.commit()
