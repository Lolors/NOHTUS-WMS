from nohtus.db import connect

def init_db():
    con = connect(); cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_code TEXT,
        standard_name TEXT NOT NULL,
        warehouse_name TEXT,
        aliases TEXT
    )
    """)
    # v3.6: ERP별 제품명/대체 매칭 메모 컬럼 추가. 기존 DB도 자동 보강.
    product_cols = {r[1] for r in cur.execute("PRAGMA table_info(products)").fetchall()}
    for col in ["erp_nohtuspharm_name", "erp_nohtus_name", "erp_noh_name", "erp_noh_code", "bidata_name", "substitute_note", "image_path"]:
        if col not in product_cols:
            cur.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT")
    cur.execute("""
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
    )
    """)
    cur.execute("""
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
        memo TEXT
    )
    """)
    tx_cols = {r[1] for r in cur.execute("PRAGMA table_info(transactions)").fetchall()}
    if "final_stock" not in tx_cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN final_stock INTEGER")
    if "actor" not in tx_cols:
        cur.execute("ALTER TABLE transactions ADD COLUMN actor TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS erp_stock(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uploaded_at TEXT,
        company TEXT,
        product_name TEXT,
        lot TEXT,
        exp_date TEXT,
        qty INTEGER
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS erp_ambiguous_candidates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        erp_company TEXT NOT NULL,
        erp_name TEXT NOT NULL,
        candidate_product TEXT NOT NULL,
        memo TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_code TEXT,
        customer_name TEXT NOT NULL,
        manager TEXT,
        phone TEXT,
        address TEXT,
        memo TEXT,
        updated_at TEXT
    )
    """)
    customer_cols = {r[1] for r in cur.execute("PRAGMA table_info(customers)").fetchall()}
    for col in ["company", "customer_type"]:
        if col not in customer_cols:
            cur.execute(f"ALTER TABLE customers ADD COLUMN {col} TEXT")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS erp_upload_decisions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decided_at TEXT NOT NULL,
        erp_company TEXT NOT NULL,
        erp_name TEXT NOT NULL,
        selected_product TEXT NOT NULL,
        memo TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS outbound_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        order_date TEXT NOT NULL,
        title TEXT,
        status TEXT DEFAULT '저장됨',
        memo TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS outbound_order_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        inventory_id INTEGER,
        location TEXT,
        product_name TEXT,
        lot TEXT,
        exp_date TEXT,
        qty INTEGER NOT NULL,
        company TEXT,
        warehouse_name TEXT,
        FOREIGN KEY(order_id) REFERENCES outbound_orders(id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_match_conflict_approvals(
        company TEXT NOT NULL,
        source_name TEXT NOT NULL,
        approved_at TEXT,
        PRIMARY KEY(company, source_name)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mobile_favorites(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        product_name TEXT NOT NULL,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT,
        UNIQUE(username, product_name)
    )
    """)
    fav_cols = {r[1] for r in cur.execute("PRAGMA table_info(mobile_favorites)").fetchall()}
    if "sort_order" not in fav_cols:
        cur.execute("ALTER TABLE mobile_favorites ADD COLUMN sort_order INTEGER DEFAULT 0")

    # v3.8: 더미데이터 자동 생성 중단.
    # 처음 실행 시 제품/재고는 비어 있으며, 제품마스터 엑셀 또는 재고조사 엑셀 업로드로 채웁니다.
    con.commit(); con.close()
