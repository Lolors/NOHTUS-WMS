from datetime import date
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import pandas as pd

from nohtus.export_app.services import dashboard_view_service, export_confirm_service, wms_link_service
from nohtus.export_app.services import wms_link_edit_patch
from nohtus.export_app.views.실출고_입력 import recommended_inventory_search_term


class ExportIntegrationFollowupTests(TestCase):
    def setUp(self):
        # list_active_orders()는 @st.cache_data로 캐싱되어 실제 WMS DB 파일이
        # 바뀌어야 무효화된다. 아래 테스트들은 wms_q 자체를 목으로 바꿔치기해
        # 실제 파일을 건드리지 않으므로, 캐시를 비워두지 않으면 한 테스트의
        # 목 결과가 다음 테스트로 새어 들어간다.
        export_confirm_service._cached_active_orders.clear()

    def test_sales_registration_lists_confirmed_orders_after_waiting_orders(self):
        with patch.object(export_confirm_service, "wms_q", return_value=pd.DataFrame()) as query:
            export_confirm_service.list_active_orders()

        sql = query.call_args.args[0]
        self.assertIn("status IN ('waiting','partial','confirmed')", sql)
        self.assertLess(sql.index("WHEN 'waiting' THEN 0"), sql.index("WHEN 'partial' THEN 1"))
        self.assertLess(sql.index("WHEN 'partial' THEN 1"), sql.index("WHEN 'confirmed' THEN 2"))

    def test_sales_registration_order_table_is_seventy_viewport_width_and_colors_status(self):
        source = Path("nohtus/export_app/views/수출확정_매출_등록.py").read_text(encoding="utf-8")
        self.assertIn('[class*="st-key-export_sales_registration_orders"]', source)
        self.assertIn("width: 70vw !important", source)
        self.assertIn("'confirmed': '수출확정'", source)
        self.assertIn("'수출확정': 'background-color: #dcfce7", source)
        self.assertIn("'수출대기': 'background-color: #dff3ff", source)

    def test_ctn_packing_filters_and_export_waiting_labels(self):
        packing = Path('nohtus/export_app/views/박스_패킹_edit.py').read_text(encoding='utf-8')
        selector = Path('nohtus/export_app/components/case_selector.py').read_text(encoding='utf-8')
        intake = Path('nohtus/export_app/views/실출고_입력.py').read_text(encoding='utf-8')
        self.assertIn("show_stage=False", packing)
        self.assertIn("show_transport=True", packing)
        self.assertIn("case_label='product_summary'", packing)
        self.assertIn("'수출번호 및 주문 요약'", selector)
        self.assertIn("st.markdown('### 수출대기 저장제품')", intake)
        self.assertNotIn("st.markdown('### 실제 수출대기 저장제품')", intake)
        self.assertIn("format='%g'", intake)
        self.assertNotIn("format='%g EA'", intake)

    def test_inventory_recommendation_stops_before_first_parenthesis(self):
        self.assertEqual(recommended_inventory_search_term('제품 A (10 EA)'), '제품 A')
        self.assertEqual(recommended_inventory_search_term('  제품 B(5EA)  '), '제품 B')
        self.assertEqual(recommended_inventory_search_term('괄호 없는 제품'), '괄호 없는 제품')

    def test_confirmation_edit_fields_are_clean_four_column_layout(self):
        source = Path('nohtus/export_app/views/주문_검색_및_수정.py').read_text(encoding='utf-8')
        self.assertIn("st.markdown('### 수출확정')", source)
        self.assertIn('company_col, search_col, customer_col, date_col = st.columns(4)', source)
        for old_label in (
            '수정할 ERP 매출 사업장', '수정할 ERP 수출 매출처 검색',
            '수정할 ERP 수출 매출처', '수정할 출고일자',
        ):
            self.assertNotIn(old_label, source)

    def test_confirmed_sales_registration_remains_editable(self):
        source = Path("nohtus/export_app/views/주문_검색_및_수정.py").read_text(encoding="utf-8")
        self.assertIn("['waiting', 'partial', 'confirmed']", source)
        self.assertIn("확정 품목 매출·출고 등록 및 수정", source)
        self.assertIn("update_confirmed_export_waiting_items", source)

    def test_sales_registration_uses_quantity_ranked_order_summary_and_confirmation_counts(self):
        orders = pd.DataFrame([{
            'id': 1, 'export_no': 'EXP-1', 'country': 'KR', 'buyer': 'B',
            'transport_method': 'AIR', 'title': 'old', 'status': 'waiting',
            'order_date': '', 'created_at': '',
        }])
        items = pd.DataFrame([
            {'order_id': 1, 'product_name': '소량', 'qty': 2, 'confirmed': 1, 'confirmed_company': 'NOH', 'confirmed_customer_name': 'A'},
            {'order_id': 1, 'product_name': '최다', 'qty': 6, 'confirmed': 1, 'confirmed_company': '노투스', 'confirmed_customer_name': 'B'},
            {'order_id': 1, 'product_name': '최다', 'qty': 4, 'confirmed': 1, 'confirmed_company': 'NOH', 'confirmed_customer_name': 'C'},
            {'order_id': 1, 'product_name': '차순위', 'qty': 5, 'confirmed': 0, 'confirmed_company': None, 'confirmed_customer_name': None},
        ])
        with patch.object(export_confirm_service, 'wms_q', side_effect=[orders, items]):
            result = export_confirm_service.list_active_orders()
        self.assertEqual(result.loc[0, 'order_summary'], '최다 10EA, 차순위 5EA + 그 외 1품목')
        self.assertEqual(result.loc[0, 'confirmed_company_count'], 2)
        self.assertEqual(result.loc[0, 'confirmed_customer_count'], 3)

        view = Path('nohtus/export_app/views/수출확정_매출_등록.py').read_text(encoding='utf-8')
        self.assertIn("'주문 요약': orders['order_summary']", view)
        self.assertIn("str(label) if int(count) == 1 else f'{int(count)}곳'", view)
        self.assertLess(view.index("'상태':"), view.index("'수출번호':"))

    def test_confirmation_items_offer_source_company_bulk_selection(self):
        source = Path('nohtus/export_app/views/주문_검색_및_수정.py').read_text(encoding='utf-8')
        self.assertIn("f'{company} 전체 선택'", source)
        self.assertIn("source['출고사업장']", source)
        self.assertIn("st.session_state[selected_key] = sorted(company_ids)", source)
        self.assertNotIn("selected_ids.update(company_ids)", source)
        self.assertLess(source.index("edited = st.data_editor("), source.index("f'{company} 전체 선택'"))
        self.assertGreaterEqual(source.count('_company_selection_editor('), 3)

    def test_single_confirmation_uses_its_name_and_dashboard_is_seventy_viewport_width(self):
        orders = pd.DataFrame([{
            'id': 1, 'export_no': 'EXP-1', 'country': 'KR', 'buyer': 'B',
            'transport_method': 'AIR', 'title': 'old', 'status': 'confirmed',
            'order_date': '', 'created_at': '',
        }])
        items = pd.DataFrame([{
            'order_id': 1, 'product_name': '제품', 'qty': 1, 'confirmed': 1,
            'confirmed_company': '노투스', 'confirmed_customer_name': '수출처 A',
        }])
        with patch.object(export_confirm_service, 'wms_q', side_effect=[orders, items]):
            result = export_confirm_service.list_active_orders()
        self.assertEqual(result.loc[0, 'confirmed_company_label'], '노투스')
        self.assertEqual(result.loc[0, 'confirmed_customer_label'], '수출처 A')

        dashboard = Path('nohtus/export_app/views/오버뷰.py').read_text(encoding='utf-8')
        self.assertIn("st.container(key='export_dashboard_active_orders_panel')", dashboard)
        self.assertIn('st-key-export_dashboard_active_orders_panel', dashboard)
        # f32d5a8에서 대시보드 표 너비를 70vw에서 60vw로 의도적으로 조정했다.
        self.assertIn('width: 60vw !important', dashboard)

    def test_duplicate_open_export_numbers_require_merge_or_new_number(self):
        # wms_link_edit_patch가 모듈 임포트 시점에 wms_link_service._find_open_order_id
        # 자체를 자신의 _editable_order_id로 영구히 바꿔치기하므로(export_app_pages.py
        # 임포트만 되면 프로세스 전체에 적용됨), 실제로 호출되는 건 항상 이쪽이다.
        # wms_link_service.wms_q를 모킹해도 이 함수는 그걸 안 보므로 효과가 없다.
        rows = pd.DataFrame([{"id": 11, "status": "waiting"}, {"id": 12, "status": "partial"}])
        with patch.object(wms_link_edit_patch, "wms_q", return_value=rows):
            with self.assertRaisesRegex(ValueError, "병합하거나 새 수출번호"):
                wms_link_service._find_open_order_id("EXP-2026-001")

    def test_wms_failure_restores_original_export_rows(self):
        case = {"export_no": "EXP-1", "country": "KR", "buyer": "Buyer", "transport_mode": "AIR"}
        original = [{
            "id": 21, "order_item_id": 7, "business_unit": "NOH",
            "source_location": "A1-01-01", "source_inventory_id": 101,
            "product_name": "제품", "lot_no": "LOT", "expiry_date": "2027-01-01",
            "requested_qty": 2,
        }]
        replacement = [{**original[0], "requested_qty": 1}]
        # save_picked_inventory 자체가 wms_link_edit_patch에 의해 통째로
        # 바꿔치기되어 있으므로(주석 참고), _find_open_order_id/
        # save_export_waiting_order는 wms_link_service가 아니라
        # wms_link_edit_patch 쪽 이름을 모킹해야 실제로 적용된다.
        # export_service/shipment_service는 두 모듈이 같은 객체를 가리키므로
        # 어느 쪽을 패치해도 동일하다.
        with (
            patch.object(wms_link_service.export_service, "get_case", return_value=case),
            patch.object(wms_link_service.shipment_service, "list_case_items", return_value=original),
            patch.object(wms_link_edit_patch, "_editable_order_id", return_value=5),
            patch.object(wms_link_edit_patch, "_rows_with_live_source_inventory", return_value=replacement),
            patch.object(wms_link_service.shipment_service, "save_for_order", return_value=1) as save_export,
            patch.object(
                wms_link_edit_patch.export_waiting_service,
                "save_export_waiting_order",
                side_effect=RuntimeError("WMS failure"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "WMS failure"):
                wms_link_service.save_picked_inventory(
                    case_id=1, order_item_id=7, kept_rows=replacement, picked_rows=[]
                )
        self.assertEqual(save_export.call_count, 2)
        restored_rows = save_export.call_args_list[1].args[2]
        self.assertEqual(restored_rows[0]["requested_qty"], 2.0)

    def test_saving_a_new_pick_does_not_retry_an_orphan_waiting_product(self):
        case = {
            "export_no": "EXP-1", "country": "KR", "buyer": "Buyer",
            "transport_mode": "AIR",
        }
        orphan_waiting = [{
            "source_inventory_id": 11, "company": "NOH", "product_name": "Larapiel",
            "warehouse_name": "", "lot": "OLD", "exp_date": "2029-01-01",
            "source_location": "P", "qty": 2,
        }]
        new_pick = [{
            "inventory_id": 22, "company": "NOH", "product_name": "Doctor Kim",
            "lot": "S103", "exp_date": "2029-07-23", "location": "REC", "qty": 10,
        }]
        with (
            patch.object(wms_link_service.export_service, "get_case", return_value=case),
            patch.object(wms_link_service.shipment_service, "list_case_items", return_value=[]),
            patch.object(wms_link_service.shipment_service, "save_for_order", return_value=10),
            patch.object(wms_link_edit_patch, "_editable_order_id", return_value=5),
            patch.object(wms_link_service, "_waiting_rows_for_order", return_value=orphan_waiting),
            patch.object(wms_link_edit_patch, "_rows_with_live_source_inventory", return_value=[]),
            patch.object(
                wms_link_edit_patch.export_waiting_service,
                "save_export_waiting_order",
                return_value={"order_id": 5},
            ) as save_waiting,
            patch.object(wms_link_service, "sync_mirror_source_links") as sync_links,
        ):
            wms_link_service.save_picked_inventory(
                case_id=1, order_item_id=7, kept_rows=[], picked_rows=new_pick
            )

        cart = save_waiting.call_args.args[0]
        self.assertEqual([int(row["id"]) for row in cart], [22])
        sync_links.assert_called_once_with(1, 5)

    def test_stale_source_id_relinks_to_existing_p_inventory_without_new_move(self):
        row = {
            "source_inventory_id": 11765, "business_unit": "NOHTUS",
            "product_name": "JS Tox", "lot_no": "LOT-1",
            "expiry_date": "2027-11-03", "source_location": "R1",
            "requested_qty": 20,
        }
        p_inventory = pd.DataFrame([{"id": 12199, "location": "P", "qty": 40}])
        with (
            patch.object(wms_link_edit_patch, "connect") as connect,
            patch.object(wms_link_edit_patch, "wms_q", return_value=p_inventory),
        ):
            connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
            wms_link_edit_patch._fill_source_links([row], [])

        self.assertEqual(row["source_inventory_id"], 12199)
        self.assertEqual(row["source_location"], "P")

    def test_zero_quantity_p_row_falls_back_to_sufficient_source_stock(self):
        row = {
            "source_inventory_id": 11745, "business_unit": "NOHTUS",
            "product_name": "Larapiel", "lot_no": "EAS1",
            "expiry_date": "2029-01-19", "source_location": "REC",
            "requested_qty": 2,
        }
        inventories = pd.DataFrame([
            {"id": 12146, "location": "P", "qty": 0},
            {"id": 12359, "location": "REC", "qty": 2},
        ])
        with (
            patch.object(wms_link_edit_patch, "connect") as connect,
            patch.object(wms_link_edit_patch, "wms_q", return_value=inventories),
        ):
            connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
            wms_link_edit_patch._fill_source_links([row], [])

        self.assertEqual(row["source_inventory_id"], 12359)
        self.assertEqual(row["source_location"], "REC")

    def test_dashboard_orders_early_stages_before_domestic_delivery(self):
        cases = [
            {
                "id": 3, "case_type": "current", "stage": "국내배송",
                "actual_ship_date": "2026-08-10", "created_at": "2026-08-01",
            },
            {
                "id": 1, "case_type": "current", "stage": "주문 접수",
                "actual_ship_date": "", "created_at": "2026-08-11",
            },
            {
                "id": 2, "case_type": "current", "stage": "입고 진행",
                "actual_ship_date": "", "created_at": "2026-08-09",
            },
        ]
        with patch.object(dashboard_view_service.order_service, "list_editable_cases", return_value=cases):
            result = dashboard_view_service.active_and_recent_cases(reference=date(2026, 8, 11))
        self.assertEqual([row["id"] for row in result], [1, 2, 3])

    def test_export_menu_is_conditionally_rendered_and_has_bottom_collapse(self):
        source = Path("nohtus/navigation.py").read_text(encoding="utf-8")
        self.assertIn('if not expanded:', source)
        self.assertIn('"수출 메뉴 접기"', source)
        self.assertNotIn('export_menu_hover_zone', source)

    def test_overview_column_order_and_todo_removal(self):
        source = Path("nohtus/export_app/views/오버뷰.py").read_text(encoding="utf-8")
        positions = [source.index(f"'{label}'") for label in (
            "국가", "바이어", "운송방식", "단계", "입고 진행률", "주문목록"
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("내가 체크할 일", source)

    def test_duplicate_active_links_are_not_silently_reduced_to_first_row(self):
        source = Path("nohtus/export_app/views/주문_검색_및_수정.py").read_text(encoding="utf-8")
        duplicate_guard = source.index("if len(active_rows.index) > 1:")
        first_row_use = source.index("active_rows.iloc[0]")
        self.assertLess(duplicate_guard, first_row_use)
        self.assertIn("주문 병합으로 하나로 합치거나", source)

    def test_export_sales_registration_is_after_shipment_intake(self):
        navigation = Path("nohtus/navigation.py").read_text(encoding="utf-8")
        self.assertLess(navigation.index('"수출대기 저장"'), navigation.index('"수출확정 매출 등록"'))
        self.assertLess(navigation.index('"수출확정 매출 등록"'), navigation.index('"박스 패킹"'))

        application = Path("nohtus/application.py").read_text(encoding="utf-8")
        self.assertIn('elif menu == "수출확정 매출 등록": page_export_sales_registration()', application)

    def test_confirmation_was_removed_from_order_edit_and_moved_to_own_page(self):
        order_edit = Path("nohtus/export_app/views/주문_검색_및_수정.py").read_text(encoding="utf-8")
        dedicated = Path("nohtus/export_app/views/수출확정_매출_등록.py").read_text(encoding="utf-8")
        self.assertNotIn("render_wms_confirmation_section(case['export_no'])", order_edit)
        self.assertIn("render_wms_confirmation_section(\n        export_no,", dedicated)
        self.assertNotIn("_HideDuplicateConfirmationSection", dedicated)
        self.assertNotIn("st.markdown = patched_markdown", dedicated)
        self.assertIn("shipment_date_label='등록일자'", dedicated)
        self.assertIn("주문을 병합하거나 새 수출번호를 사용하세요", dedicated)

    def test_confirmation_items_include_standard_and_source_erp_names(self):
        raw = pd.DataFrame([{
            "id": 1,
            "출고사업장": "NOH",
            "원래로케이션": "A1-01-01",
            "표준제품명": "표준 제품",
            "출고사업장ERP명": "ERP 검색 제품명",
            "LOT": "L1",
            "유통기한": "2027-01-01",
            "수량": 2,
            "confirmed": 0,
            "확정사업장": None,
            "확정매출처": None,
            "확정일시": None,
        }])
        with patch.object(export_confirm_service, "wms_q", return_value=raw):
            result = export_confirm_service.order_items(1)
        self.assertEqual(result.loc[0, "표준제품명"], "표준 제품")
        self.assertEqual(result.loc[0, "출고사업장ERP명"], "ERP 검색 제품명")
