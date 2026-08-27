from nohtus.db import connect


_PROMO_LOCATION_NORMALIZED = "N홍보물랙"


def _migrate_promo_rack_locations(cur):
    """Move legacy N promo-rack references to the standalone promo rack.

    Normalizing whitespace, hyphens and underscores covers values used by older
    picker versions (for example ``N-홍보물랙`` and ``N - 홍보물랙``).  The UPDATEs
    are safe to run on every startup and keep both live inventory and textual
    history/order references aligned without changing inventory row ids.
    """
    predicate = (
        "REPLACE(REPLACE(REPLACE(UPPER(TRIM(COALESCE({column},''))), ' ', ''), '-', ''), '_', '')=?"
    )
    for table, column in (
        ("inventory", "location"),
        ("transactions", "from_location"),
        ("transactions", "to_location"),
        ("outbound_order_items", "location"),
    ):
        cur.execute(
            f"UPDATE {table} SET {column}='홍보물랙' WHERE " + predicate.format(column=column),
            (_PROMO_LOCATION_NORMALIZED,),
        )

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
    if "is_material" not in product_cols:
        cur.execute("ALTER TABLE products ADD COLUMN is_material INTEGER NOT NULL DEFAULT 0")
    if "material_type" not in product_cols:
        cur.execute("ALTER TABLE products ADD COLUMN material_type TEXT")
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
    inventory_cols = {r[1] for r in cur.execute("PRAGMA table_info(inventory)").fetchall()}
    if "is_shippable" not in inventory_cols:
        cur.execute("ALTER TABLE inventory ADD COLUMN is_shippable INTEGER NOT NULL DEFAULT 1")
    if "location_range_end" not in inventory_cols:
        # 한 제품이 실제로는 여러 로케이션(구역-라인-단) 범위를 통째로 차지하지만
        # 어느 칸에서 실제로 빠지는지 관리하고 싶지 않을 때, location(시작 칸)에서
        # 이 칸(끝 칸)까지의 전체 블록을 로케이션맵에 "채워짐"으로 표시하는 데 쓴다.
        # 실제 수량/이동/피킹 로직은 그대로 location 하나만 기준으로 동작한다.
        cur.execute("ALTER TABLE inventory ADD COLUMN location_range_end TEXT")
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

    # 수출확정도 실제 매출 출고이므로 일반 출고지시 이력으로 통일한다.
    # 과거에 '출고'로 저장된 수출확정 이력도 앱 시작 시 함께 보정한다.
    cur.execute("""
        UPDATE transactions
        SET tx_type='출고지시'
        WHERE tx_type='출고'
          AND TRIM(COALESCE(memo,'')) LIKE '수출확정 /%'
    """)
    cur.execute("DROP TRIGGER IF EXISTS trg_export_confirm_as_outbound_history")
    cur.execute("""
        CREATE TRIGGER trg_export_confirm_as_outbound_history
        AFTER INSERT ON transactions
        WHEN NEW.tx_type='출고'
         AND TRIM(COALESCE(NEW.memo,'')) LIKE '수출확정 /%'
        BEGIN
            UPDATE transactions
            SET tx_type='출고지시'
            WHERE id=NEW.id;
        END
    """)

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
    CREATE TABLE IF NOT EXISTS purchase_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT NOT NULL,
        purchase_date TEXT NOT NULL,
        supplier_name TEXT NOT NULL,
        erp_product_name TEXT NOT NULL,
        specification TEXT,
        quantity REAL,
        unit_price REAL,
        note TEXT,
        standard_product_name TEXT,
        source_file TEXT,
        imported_at TEXT,
        duplicate_key TEXT UNIQUE
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_history_standard ON purchase_history(standard_product_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_history_erp_name ON purchase_history(erp_product_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_history_date ON purchase_history(purchase_date)")
    # High-frequency outbound screens filter these tables on every Streamlit
    # rerun.  Existing installations receive the indexes during normal startup.
    cur.execute("CREATE INDEX IF NOT EXISTS idx_inventory_product_company_qty ON inventory(product_name, company, qty)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(tx_type)")
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_outbound_items_order ON outbound_order_items(order_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_outbound_items_product_order ON outbound_order_items(product_name, order_id)")
    outbound_order_cols = {
        r[1] for r in cur.execute("PRAGMA table_info(outbound_orders)").fetchall()
    }
    if "customer_name" not in outbound_order_cols:
        cur.execute("ALTER TABLE outbound_orders ADD COLUMN customer_name TEXT")
    if "customer_company" not in outbound_order_cols:
        cur.execute("ALTER TABLE outbound_orders ADD COLUMN customer_company TEXT")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_bom_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        finished_product TEXT NOT NULL,
        material_product TEXT NOT NULL,
        quantity_per REAL NOT NULL DEFAULT 1,
        updated_at TEXT,
        UNIQUE(finished_product, material_product)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_product_bom_finished ON product_bom_items(finished_product)")
    _migrate_promo_rack_locations(cur)
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
