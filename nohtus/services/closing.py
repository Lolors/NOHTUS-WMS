"""Service helpers."""

from __future__ import annotations


def _infer_customer_from_title(title, customers_df=None):
    """출고지시서 제목에서 거래처명을 추정한다.
    제목 규칙: [출고처] [첫 제품명] 외 x품목.
    거래처 관리에 등록된 이름 중 title 시작과 일치하는 가장 긴 이름을 우선 사용한다.
    """
    title = str(title or "").strip()
    if not title:
        return "", ""
    if customers_df is None:
        customers_df = q("SELECT customer_name, manager FROM customers ORDER BY LENGTH(customer_name) DESC")
    if not customers_df.empty:
        for r in customers_df.itertuples():
            name = str(getattr(r, "customer_name", "") or "").strip()
            if name and title.startswith(name):
                return name, str(getattr(r, "manager", "") or "")
    # 거래처 관리에 없으면 제목 첫 토큰을 임시 출고처로 사용한다.
    return title.split()[0] if title.split() else title, ""


def _extract_inbound_source_from_memo(memo):
    """입고 이력 memo에서 입고처만 추출한다.
    저장 형식 예: '매입처: 거래처명 / 기타메모'
    """
    text = str(memo or "").strip()
    if not text or text == "입고 등록":
        return ""
    prefixes = ["매입처:", "입고처:"]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            if " / " in text:
                text = text.split(" / ", 1)[0].strip()
            break
    return text


def dataframe_to_excel_bytes(df, sheet_name="Sheet1"):
    """DataFrame을 엑셀 bytes로 변환한다.
    openpyxl이 허용하지 않는 제어문자/특수 공백은 저장 전에 전부 제거한다.
    """
    bio = BytesIO()
    safe_df = df.copy() if df is not None else pd.DataFrame()
    safe_sheet = clean_excel_text(sheet_name)[:31] or "Sheet1"
    safe_df.columns = [clean_excel_text(c) for c in safe_df.columns]
    for col in safe_df.columns:
        if safe_df[col].dtype == object:
            safe_df[col] = safe_df[col].apply(lambda v: clean_excel_text(v) if v is not None else "")
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        safe_df.to_excel(writer, index=False, sheet_name=safe_sheet)
        ws = writer.book[safe_sheet]
        from openpyxl.styles import Border, Side, Font, PatternFill, Alignment
        thin = Side(style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill("solid", fgColor="E5E7EB")
        for col in ws.columns:
            max_len = 10
            letter = col[0].column_letter
            for cell in col:
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if cell.row == 1:
                    cell.font = Font(bold=True)
                    cell.fill = header_fill
                max_len = max(max_len, len(str(cell.value or "")) + 2)
            ws.column_dimensions[letter].width = min(max_len, 42)
        if safe_sheet == "마감체크":
            # 마감 체크리스트 전용 서식: C열은 좁게, D열은 제품명 확인용으로 넓게.
            ws.column_dimensions["C"].width = 14
            ws.column_dimensions["D"].width = 50
            # 현재수량 컬럼은 연한 하늘색으로 표시한다.
            from openpyxl.styles import PatternFill
            current_fill = PatternFill("solid", fgColor="DDEBF7")
            header_map = {str(ws.cell(row=1, column=i).value or "").strip(): i for i in range(1, ws.max_column + 1)}
            cur_col = header_map.get("현재수량")
            if cur_col:
                for rr in range(1, ws.max_row + 1):
                    ws.cell(row=rr, column=cur_col).fill = current_fill
        ws.freeze_panes = "A2"
        if safe_df.shape[1] > 0:
            ws.auto_filter.ref = ws.dimensions
    bio.seek(0)
    return bio.getvalue()


def page_erp_stock_compare():
    st.title("ERP 재고 비교")
    st.caption("ERP/WMS 모두 해당 사업장의 ERP명 기준으로 제조번호·유통기한 없이 총수량만 비교합니다. 비자료는 비교 대상에서 제외합니다.")

    parsed = []
    cols = st.columns(3, gap="large")
    info = [("노투스팜", "SIMS"), ("NOH", "SIMS"), ("노투스", "IBK우리은행 전산")]
    for col, (company, system_name) in zip(cols, info):
        with col:
            st.markdown(f"### {company}")
            st.caption(system_name)
            up = st.file_uploader(f"{company} 현재고 엑셀", type=["xlsx", "xls"], key=f"erp_compare_upload_{company}")
            if up is not None:
                parsed.append(_read_erp_current_file(up, company, "compare"))
                st.success("파일 선택됨")
            else:
                parsed.append(None)

    if not any(parsed):
        st.info("노투스팜 / NOH / 노투스 ERP 현재고 엑셀을 업로드하세요.")
        return

    _, run_col, _ = st.columns([3, 2, 3], gap="large")
    with run_col:
        run_compare = st.button("ERP 재고 비교 실행", type="primary", use_container_width=True)

    if run_compare:
        erp, amb, fail, auto_count = _normalize_erp_current_rows(parsed)

        wms_raw = q("""SELECT company AS 사업장, product_name AS 표준제품명, SUM(qty) AS 수량
                       FROM inventory
                       WHERE qty<>0 AND company IN ('노투스팜','NOH','노투스')
                       GROUP BY company, product_name""")
        if wms_raw.empty:
            wms_sum = pd.DataFrame(columns=["사업장", "제품명", "WMS수량"])
        else:
            wms_raw["제품명"] = wms_raw.apply(lambda r: clean_excel_text(product_compare_name_for(r["사업장"], r["표준제품명"])), axis=1)
            wms_raw = wms_raw[~wms_raw["제품명"].apply(is_ignored_erp_product_name)]
            wms_sum = (
                wms_raw.groupby(["사업장", "제품명"], as_index=False)["수량"]
                .sum()
                .rename(columns={"수량": "WMS수량"})
            )

        comp = wms_sum.merge(erp, how="outer", on=["사업장", "제품명"])
        if comp.empty:
            comp = pd.DataFrame(columns=["사업장", "제품명", "ERP수량", "WMS수량", "차이"])
        else:
            comp["ERP수량"] = comp["ERP수량"].fillna(0).astype(int)
            comp["WMS수량"] = comp["WMS수량"].fillna(0).astype(int)
            comp["차이"] = comp["WMS수량"] - comp["ERP수량"]
            comp = comp[["사업장", "제품명", "ERP수량", "WMS수량", "차이"]].sort_values(["사업장", "제품명"])

        st.session_state["erp_compare_rows"] = comp.to_dict("records")
        st.session_state["erp_compare_amb"] = amb.to_dict("records") if not amb.empty else []
        st.session_state["erp_compare_fail"] = fail.to_dict("records") if not fail.empty else []
        st.session_state["erp_compare_summary"] = {"auto": auto_count, "amb": len(amb), "fail": len(fail)}

    if "erp_compare_summary" in st.session_state:
        sm = st.session_state["erp_compare_summary"]
        m1, m2, m3 = st.columns(3)
        m1.metric("ERP 행 반영", f"{sm['auto']}건")
        m2.metric("확인 필요", f"{sm['amb']}건")
        m3.metric("매칭 실패", f"{sm['fail']}건")
        comp = pd.DataFrame(st.session_state.get("erp_compare_rows", []))
        amb = pd.DataFrame(st.session_state.get("erp_compare_amb", []))
        fail = pd.DataFrame(st.session_state.get("erp_compare_fail", []))
        if not comp.empty:
            st.markdown("### 재고 비교 결과")
            only_diff = st.checkbox("차이 있는 항목만 보기", value=True, key="erp_compare_only_diff")
            shown = comp[comp["차이"] != 0] if only_diff else comp
            st.dataframe(shown, use_container_width=True, hide_index=True)
            st.download_button(
                "비교 결과 엑셀 다운로드",
                data=dataframe_to_excel_bytes(comp, "ERP_WMS_비교"),
                file_name=f"NOHTUS_ERP_WMS_비교_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        if not amb.empty:
            st.warning("확인 필요 항목")
            st.dataframe(amb, use_container_width=True, hide_index=True)
        if not fail.empty:
            st.error("매칭 실패 항목")
            st.dataframe(fail, use_container_width=True, hide_index=True)
