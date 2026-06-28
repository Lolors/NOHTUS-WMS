-- NOHTUS WMS schema reference
-- 실제 DB는 app.py init_db()에서 자동 생성/보강됩니다.

CREATE TABLE IF NOT EXISTS products(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT,
    standard_name TEXT NOT NULL,
    warehouse_name TEXT,
    aliases TEXT,
    erp_nohtuspharm_name TEXT,
    erp_nohtus_name TEXT,
    erp_noh_name TEXT,
    erp_noh_code TEXT,
    bidata_name TEXT,
    substitute_note TEXT,
    image_path TEXT
);

CREATE TABLE IF NOT EXISTS inventory(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    product_name TEXT NOT NULL,
    warehouse_name TEXT,
    lot TEXT,
    exp_date TEXT,
    location TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS transactions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    tx_type TEXT NOT NULL,
    product_name TEXT NOT NULL,
    warehouse_name TEXT,
    lot TEXT,
    exp_date TEXT,
    from_company TEXT,
    from_location TEXT,
    to_company TEXT,
    to_location TEXT,
    qty INTEGER NOT NULL,
    memo TEXT,
    final_stock INTEGER
);
