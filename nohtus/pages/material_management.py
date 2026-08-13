from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from nohtus.db import connect, q
from nohtus.services.inventory import insert_transaction_log


_TRUE_MATERIAL_VALUES = ("1", "true", "yes", "y", "o", "v", "체크", "부자재")
MATERIAL_TYPES = ("패키지", "라벨", "트레이", "코팅타이벡", "배너", "브로슈어", "책자", "쇼핑백", "기타")


def ensure_bom_table():
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS product_bom_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finished_product TEXT NOT NULL,
                material_product TEXT NOT NULL,
                quantity_per REAL NOT NULL DEFAULT 1,
                updated_at TEXT,
                UNIQUE(finished_product, material_product)
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_product_bom_finished ON product_bom_items(finished_product)")
        con.commit()


def material_products():
    placeholders = ",".join("?" for _ in _TRUE_MATERIAL_VALUES)
    return q(
        f"""
        SELECT TRIM(standard_name) AS standard_name,
               GROUP_CONCAT(DISTINCT NULLIF(TRIM(COALESCE(erp_nohtuspharm_name,'')),'')) AS erp_names
        FROM products
        WHERE LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT))) IN ({placeholders})
          AND TRIM(COALESCE(standard_name,''))<>''
        GROUP BY TRIM(standard_name)
        ORDER BY TRIM(standard_name)
        """,
        _TRUE_MATERIAL_VALUES,
    )


def material_inventory_summary():
    placeholders = ",".join("?" for _ in _TRUE_MATERIAL_VALUES)
    return q(
        f"""
        WITH material_names AS (
            SELECT TRIM(standard_name) AS standard_name,
                   COALESCE(NULLIF(MAX(TRIM(COALESCE(material_type,''))),''), '') AS material_type
            FROM products
            WHERE LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT))) IN ({placeholders})
              AND TRIM(COALESCE(standard_name,''))<>''
            GROUP BY TRIM(standard_name)
        )
        SELECT m.material_type AS material_type,
               m.standard_name AS standard_name,
               COALESCE(NULLIF(TRIM(i.company),''), '-') AS company,
               CASE
                   WHEN TRIM(COALESCE(i.company,''))='비자료' THEN ''
                   ELSE COALESCE(NULLIF(TRIM(i.warehouse_name),''), '-')
               END AS erp_name,
               COALESCE(SUM(i.qty), 0) AS qty
        FROM material_names m
        LEFT JOIN inventory i ON TRIM(COALESCE(i.product_name,''))=m.standard_name
        GROUP BY m.material_type, m.standard_name,
                 COALESCE(NULLIF(TRIM(i.company),''), '-'),
                 CASE
                     WHEN TRIM(COALESCE(i.company,''))='비자료' THEN ''
                     ELSE COALESCE(NULLIF(TRIM(i.warehouse_name),''), '-')
                 END
        ORDER BY m.standard_name, company, erp_name
        """,
        _TRUE_MATERIAL_VALUES,
    )


def material_candidates(term=""):
    term = str(term or "").strip()
    like = f"%{term}%"
    return q(
        """
        SELECT TRIM(standard_name) AS standard_name,
               GROUP_CONCAT(DISTINCT NULLIF(TRIM(COALESCE(erp_nohtuspharm_name,'')),'')) AS erp_names
        FROM products
        WHERE TRIM(COALESCE(standard_name,''))<>''
          AND LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT)))
              NOT IN ('1','true','yes','y','o','v','체크','부자재')
          AND (?='' OR standard_name LIKE ? OR COALESCE(aliases,'') LIKE ?
               OR COALESCE(erp_nohtuspharm_name,'') LIKE ?
               OR COALESCE(erp_nohtus_name,'') LIKE ? OR COALESCE(erp_noh_name,'') LIKE ?
               OR COALESCE(bidata_name,'') LIKE ?)
        GROUP BY TRIM(standard_name)
        ORDER BY TRIM(standard_name)
        LIMIT 100
        """,
        (term, like, like, like, like, like, like),
    )


def finished_product_candidates():
    return q(
        """
        SELECT DISTINCT TRIM(standard_name) AS standard_name
        FROM products
        WHERE TRIM(COALESCE(standard_name,''))<>''
          AND LOWER(TRIM(CAST(COALESCE(is_material, 0) AS TEXT)))
              NOT IN ('1','true','yes','y','o','v','체크','부자재')
        ORDER BY TRIM(standard_name)
        """
    )


def set_material_products(product_names, is_material, material_type=""):
    names = sorted({str(name or "").strip() for name in product_names if str(name or "").strip()})
    if not names:
        return 0
    with connect() as con:
        placeholders = ",".join("?" for _ in names)
        material_type = str(material_type or "").strip()
        if material_type and material_type not in MATERIAL_TYPES:
            raise ValueError("올바른 부자재 유형을 선택하세요.")
        cur = con.execute(
            f"UPDATE products SET is_material=?, material_type=? WHERE TRIM(standard_name) IN ({placeholders})",
            (1 if is_material else 0, material_type if is_material else None, *names),
        )
        con.commit()
        return int(cur.rowcount or 0)


def update_registered_materials(original, edited):
    original = original.copy()
    edited = edited.copy()
    original["_row_key"] = original["_row_key"].astype(str)
    if "_row_key" not in edited.columns:
        edited["_row_key"] = ""
    edited["_row_key"] = edited["_row_key"].fillna("").astype(str)

    remaining_keys = set(edited["_row_key"])
    deleted = original.loc[~original["_row_key"].isin(remaining_keys), "standard_name"].astype(str).str.strip()
    deleted_names = {name for name in deleted if name}
    if "delete" in edited.columns:
        checked = edited.loc[edited["delete"].fillna(False).astype(bool), "standard_name"].astype(str).str.strip()
        deleted_names.update(name for name in checked if name)

    type_updates = {}
    for name, rows in edited.groupby("standard_name", dropna=True):
        name = str(name or "").strip()
        if not name or name in deleted_names:
            continue
        types = {str(value or "").strip() for value in rows["material_type"].tolist()}
        if len(types) > 1:
            raise ValueError(f"{name}의 유형은 모든 사업장 행에서 같아야 합니다.")
        material_type = next(iter(types), "")
        if material_type and material_type not in MATERIAL_TYPES:
            raise ValueError(f"{name}의 부자재 유형을 확인하세요.")
        type_updates[name] = material_type

    with connect() as con:
        for name in deleted_names:
            con.execute(
                "UPDATE products SET is_material=0, material_type=NULL WHERE TRIM(standard_name)=?",
                (name,),
            )
        for name, material_type in type_updates.items():
            con.execute(
                "UPDATE products SET material_type=? WHERE TRIM(standard_name)=? AND COALESCE(is_material,0)=1",
                (material_type or None, name),
            )
        con.commit()
    return len(deleted_names), len(type_updates)


def bom_finished_products():
    ensure_bom_table()
    return q("SELECT DISTINCT finished_product FROM product_bom_items ORDER BY finished_product")


def bom_items(finished_product):
    ensure_bom_table()
    return q(
        """SELECT b.id,
                  COALESCE(NULLIF(MAX(TRIM(COALESCE(p.material_type,''))),''), '') AS material_type,
                  b.material_product, b.quantity_per
           FROM product_bom_items b
           LEFT JOIN products p ON TRIM(p.standard_name)=TRIM(b.material_product)
           WHERE b.finished_product=?
           GROUP BY b.id, b.material_product, b.quantity_per
           ORDER BY b.material_product""",
        (str(finished_product or "").strip(),),
    )


def save_bom(finished_product, rows):
    finished_product = str(finished_product or "").strip()
    if not finished_product:
        raise ValueError("완제품을 선택하세요.")
    normalized = {}
    for row in rows:
        material = str(row.get("material_product") or "").strip()
        if not material or bool(row.get("delete", False)):
            continue
        try:
            quantity = float(row.get("quantity_per") or 0)
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            raise ValueError(f"{material}의 소요 수량은 0보다 커야 합니다.")
        normalized[material] = quantity

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        con.execute("DELETE FROM product_bom_items WHERE finished_product=?", (finished_product,))
        con.executemany(
            """INSERT INTO product_bom_items(finished_product, material_product, quantity_per, updated_at)
               VALUES(?,?,?,?)""",
            [(finished_product, material, quantity, now) for material, quantity in normalized.items()],
        )
        con.commit()
    return len(normalized)


def package_production_plan(finished_product, production_qty):
    finished_product = str(finished_product or "").strip()
    production_qty = int(production_qty or 0)
    if not finished_product or production_qty <= 0:
        return pd.DataFrame(columns=["material_product", "quantity_per", "required_qty", "available_qty", "remaining_qty", "shortage_qty"])
    composition = bom_items(finished_product)
    rows = []
    for item in composition.itertuples():
        raw_required = float(item.quantity_per or 0) * production_qty
        required = int(round(raw_required))
        if abs(raw_required - required) > 1e-9:
            raise ValueError(f"{item.material_product}의 계산 소요량({raw_required:g})이 정수가 아닙니다. BOM 비율 또는 생산량을 조정하세요.")
        available_df = q(
            "SELECT COALESCE(SUM(qty),0) AS qty FROM inventory WHERE TRIM(product_name)=? AND qty>0",
            (str(item.material_product).strip(),),
        )
        available = int(available_df.iloc[0]["qty"] or 0) if not available_df.empty else 0
        rows.append({
            "material_product": str(item.material_product),
            "quantity_per": float(item.quantity_per),
            "required_qty": required,
            "available_qty": available,
            "remaining_qty": available - required,
            "shortage_qty": max(required - available, 0),
        })
    return pd.DataFrame(rows)


def execute_package_production(finished_product, production_qty):
    plan = package_production_plan(finished_product, production_qty)
    if plan.empty:
        raise ValueError("저장된 BOM 구성이 없습니다.")
    shortages = plan.loc[plan["shortage_qty"] > 0]
    if not shortages.empty:
        names = ", ".join(shortages["material_product"].astype(str).tolist())
        raise ValueError(f"부자재 재고가 부족하여 생산할 수 없습니다: {names}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    production_qty = int(production_qty)
    with connect() as con:
        cur = con.cursor()
        try:
            for item in plan.itertuples():
                remaining = int(item.required_qty)
                inventory_rows = cur.execute(
                    """
                    SELECT id, company, warehouse_name, lot, exp_date, location, qty
                    FROM inventory
                    WHERE TRIM(product_name)=? AND qty>0
                    ORDER BY CASE WHEN TRIM(COALESCE(exp_date,'')) IN ('','-') THEN 1 ELSE 0 END,
                             exp_date, company, id
                    """,
                    (str(item.material_product).strip(),),
                ).fetchall()
                if sum(int(row[6] or 0) for row in inventory_rows) < remaining:
                    raise ValueError(f"생산 처리 중 {item.material_product} 재고가 변경되어 작업을 취소했습니다.")
                for inv_id, company, warehouse_name, lot, exp_date, location, available in inventory_rows:
                    if remaining <= 0:
                        break
                    take = min(remaining, int(available or 0))
                    after = int(available or 0) - take
                    cur.execute("UPDATE inventory SET qty=?, updated_at=? WHERE id=?", (after, now, int(inv_id)))
                    insert_transaction_log(
                        cur,
                        created_at=now,
                        tx_type="패키지 생산",
                        product_name=str(item.material_product),
                        warehouse_name=warehouse_name,
                        lot=lot,
                        exp_date=exp_date,
                        from_company=company,
                        from_location=location,
                        qty=take,
                        memo=f"완제품 {finished_product} {production_qty}개 생산 / BOM 부자재 차감",
                    )
                    remaining -= take
            con.commit()
        except Exception:
            con.rollback()
            raise
    return plan


def _labels(df: pd.DataFrame):
    return {
        f"{row.standard_name} | {row.erp_names or '-'}": str(row.standard_name)
        for row in df.itertuples()
    }


def _render_material_tab():
    left, right = st.columns([3, 7], gap="large")
    with left:
        st.markdown("### 부자재 추가")
        term = st.text_input(
            "제품 검색",
            placeholder="표준제품명, ERP명, 비자료명 또는 별칭",
            key="material_management_search",
        )
        candidates = material_candidates(term)
        if candidates.empty:
            st.caption("추가할 수 있는 제품이 없습니다.")
        else:
            labels = _labels(candidates)
            selected = st.multiselect(
                "부자재로 추가할 제품",
                list(labels),
                key="material_management_add_selection",
                placeholder="제품을 선택해주세요",
            )
            selected_type = st.selectbox(
                "유형",
                [""] + list(MATERIAL_TYPES),
                index=0,
                key="material_management_add_type",
                format_func=lambda value: "유형을 선택해주세요" if value == "" else value,
            )
            if st.button("선택 제품 부자재 추가", type="primary", use_container_width=True):
                if not selected:
                    st.warning("추가할 제품을 선택하세요.")
                elif not selected_type:
                    st.warning("부자재 유형을 선택하세요.")
                else:
                    set_material_products([labels[label] for label in selected], True, selected_type)
                    st.session_state.pop("material_management_add_selection", None)
                    st.session_state.pop("material_management_add_type", None)
                    st.success(f"{len(selected)}개 제품을 부자재로 추가했습니다.")
                    st.rerun()

    with right:
        st.markdown("### 등록된 부자재")
        registered = material_products()
        if registered.empty:
            st.info("등록된 부자재가 없습니다.")
            return
        source = material_inventory_summary().reset_index(drop=True)
        source["_row_key"] = source.index.astype(str)
        source["delete"] = False
        display = source.rename(columns={
            "material_type": "유형",
            "standard_name": "표준제품명",
            "company": "사업장",
            "erp_name": "ERP명",
            "qty": "수량",
        })
        edited_display = st.data_editor(
            display,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key="material_management_registered_editor",
            disabled=["표준제품명", "사업장", "ERP명", "수량"],
            column_config={
                "_row_key": None,
                "유형": st.column_config.SelectboxColumn(
                    "유형",
                    options=[""] + list(MATERIAL_TYPES),
                ),
                "delete": st.column_config.CheckboxColumn("삭제"),
            },
        )
        st.caption("열 제목을 클릭하면 오름차순/내림차순으로 정렬됩니다. 삭제에 체크하면 해당 표준제품명 전체가 부자재에서 해제됩니다.")
        if st.button("수정", type="primary", use_container_width=True):
            edited_source = edited_display.rename(columns={
                "유형": "material_type",
                "표준제품명": "standard_name",
                "사업장": "company",
                "ERP명": "erp_name",
                "수량": "qty",
                "delete": "delete",
            })
            try:
                deleted_count, updated_count = update_registered_materials(source, edited_source)
                st.session_state.pop("material_management_registered_editor", None)
                st.success(f"부자재 목록을 수정했습니다. 해제 {deleted_count}개 / 유형 반영 {updated_count}개")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def _render_bom_tab():
    ensure_bom_table()
    left, right = st.columns([3, 7], gap="large")
    existing_df = bom_finished_products()
    existing = existing_df["finished_product"].astype(str).tolist() if not existing_df.empty else []
    finished_df = finished_product_candidates()
    finished_candidates = finished_df["standard_name"].astype(str).tolist() if not finished_df.empty else []

    with left:
        st.markdown("### BOM 완제품")
        existing_term = st.text_input(
            "BOM 완제품 검색",
            placeholder="완제품명 일부를 입력하세요",
            key="bom_finished_search",
        ).strip().casefold()
        filtered_existing = [name for name in existing if existing_term in name.casefold()]
        if filtered_existing:
            selected_existing = st.radio(
                "BOM을 가진 완제품 목록",
                filtered_existing,
                index=None,
                key="bom_finished_existing",
            )
            if selected_existing:
                st.session_state["bom_active_finished"] = selected_existing
        else:
            selected_existing = ""
            if existing:
                st.info("검색 결과가 없습니다.")
            else:
                st.info("등록된 완제품 BOM이 없습니다.")
        st.markdown("#### 새 BOM 만들기")
        new_finished = st.selectbox(
            "완제품 선택",
            [""] + [name for name in finished_candidates if name not in existing],
            key="bom_new_finished",
        )
        if st.button("선택 완제품 BOM 만들기", use_container_width=True):
            if not new_finished:
                st.warning("완제품을 선택하세요.")
            else:
                st.session_state["bom_active_finished"] = new_finished
                st.rerun()

    active = str(st.session_state.get("bom_active_finished") or selected_existing or "").strip()
    if selected_existing and not st.session_state.get("bom_active_finished"):
        active = selected_existing
    with right:
        st.markdown("### BOM 구성")
        if not active:
            st.info("왼쪽에서 기존 BOM을 선택하거나 새 완제품 BOM을 만드세요.")
            return
        st.subheader(active)
        current = bom_items(active)
        editor = current.rename(columns={
            "material_type": "유형",
            "material_product": "제품명",
            "quantity_per": "소요량",
        })
        if editor.empty:
            editor = pd.DataFrame(columns=["id", "유형", "제품명", "소요량", "삭제"])
        else:
            editor["삭제"] = False
        bom_list_col, _bom_list_space = st.columns([65, 35])
        with bom_list_col:
            edited = st.data_editor(
                editor,
                hide_index=True,
                use_container_width=True,
                key=f"bom_editor_{active}",
                disabled=["id", "유형", "제품명"],
                column_config={
                    "id": None,
                    "소요량": st.column_config.NumberColumn(min_value=0.001, step=1.0),
                    "삭제": st.column_config.CheckboxColumn("삭제"),
                },
            )

        registered = material_products()
        material_names = registered["standard_name"].astype(str).tolist() if not registered.empty else []
        current_names = set(editor["제품명"].astype(str).tolist()) if not editor.empty else set()
        add_names = st.multiselect(
            "BOM에 부자재 추가",
            [name for name in material_names if name not in current_names],
            key=f"bom_add_materials_{active}",
            placeholder="제품을 선택해주세요",
        )
        default_qty = st.number_input(
            "추가 부자재의 소요량",
            min_value=0.001,
            value=1.0,
            step=1.0,
            key=f"bom_add_quantity_{active}",
        )
        if st.button("BOM 목록 저장", type="primary", use_container_width=True):
            rows = [
                {
                    "material_product": row.get("제품명"),
                    "quantity_per": row.get("소요량"),
                    "delete": row.get("삭제", False),
                }
                for _, row in edited.iterrows()
            ]
            rows.extend(
                {"material_product": name, "quantity_per": default_qty, "delete": False}
                for name in add_names
            )
            try:
                count = save_bom(active, rows)
                st.session_state.pop("bom_active_finished", None)
                st.success(f"{active} BOM을 {count}개 부자재 구성으로 저장했습니다.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def _render_package_production_tab():
    finished_df = bom_finished_products()
    finished = finished_df["finished_product"].astype(str).tolist() if not finished_df.empty else []
    if not finished:
        st.info("먼저 BOM 관리 탭에서 완제품 BOM을 등록하세요.")
        return

    input_col, preview_col = st.columns([3, 7], gap="large")
    with input_col:
        st.markdown("### 생산량 입력")
        finished_product = st.selectbox(
            "완제품",
            finished,
            key="package_production_finished",
            placeholder="제품을 선택해주세요",
        )
        production_qty = st.number_input(
            "완제품 생산 수량",
            min_value=1,
            value=1,
            step=1,
            key="package_production_qty",
        )

    with preview_col:
        st.markdown("### BOM 소요 및 재고")
        try:
            plan = package_production_plan(finished_product, production_qty)
        except ValueError as exc:
            st.error(str(exc))
            return
        if plan.empty:
            st.info("선택한 완제품의 BOM 구성이 없습니다.")
            return
        display = plan.rename(columns={
            "material_product": "부자재",
            "quantity_per": "소요량",
            "required_qty": "필요수량",
            "available_qty": "현재고",
            "remaining_qty": "차감 후 재고",
            "shortage_qty": "부족수량",
        })
        st.dataframe(display, hide_index=True, use_container_width=True)
        has_shortage = bool((plan["shortage_qty"] > 0).any())
        if has_shortage:
            st.error("부자재 재고가 부족합니다. 재고가 충분해야 전체 생산 처리가 가능합니다.")
        confirm = st.checkbox(
            f"{finished_product} {int(production_qty)}개 생산 및 부자재 재고 차감을 확인합니다.",
            key="package_production_confirm",
        )
        if st.button(
            "생산량 입력",
            type="primary",
            use_container_width=True,
            disabled=has_shortage or not confirm,
        ):
            try:
                execute_package_production(finished_product, production_qty)
                st.session_state["package_production_confirm"] = False
                st.success(f"{finished_product} {int(production_qty)}개 생산을 반영하고 BOM 부자재 재고를 차감했습니다.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def page_material_management():
    st.title("부자재 관리")
    st.caption("부자재 여부는 이 메뉴에서 등록한 제품만을 기준으로 관리합니다. 보관 구역은 부자재 판정에 영향을 주지 않습니다.")
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            width: 70vw !important;
            max-width: 70vw !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    material_tab, bom_tab, production_tab = st.tabs(["부자재 추가", "BOM 관리", "패키지 생산"])
    with material_tab:
        _render_material_tab()
    with bom_tab:
        _render_bom_tab()
    with production_tab:
        _render_package_production_tab()
