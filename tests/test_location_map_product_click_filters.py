import ast
import types
import unittest
from pathlib import Path

import pandas as pd

import nohtus.pages.location_map_business as lmb

PAGE_PATH = Path(lmb.__file__)


def _load_nested_function(name, namespace):
    tree = ast.parse(PAGE_PATH.read_text(encoding="utf-8"))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(PAGE_PATH), "exec"), namespace)
    return namespace[name]


def _load_patched_product_groups(original_product_groups, session_state=None, material_products=None):
    namespace = {
        "pd": pd,
        "st": types.SimpleNamespace(session_state=dict(session_state or {})),
        "_AVAILABLE_ONLY_KEY": lmb._AVAILABLE_ONLY_KEY,
        "_EXCLUDE_MATERIALS_KEY": lmb._EXCLUDE_MATERIALS_KEY,
        "_normalized_location": lmb._normalized_location,
        "_is_material_or_promo_location": lmb._is_material_or_promo_location,
        "_is_non_counted_location": lmb._is_non_counted_location,
        "_SPECIAL_SORT_PREFIX": lmb._SPECIAL_SORT_PREFIX,
        "material_products": set(material_products or []),
        "original_product_groups": original_product_groups,
    }
    return _load_nested_function("patched_product_groups", namespace)


class LocationMapProductClickFilterTests(unittest.TestCase):
    """제품명을 클릭했을 때 로케이션맵이 재고 분포를 만드는 patched_product_groups()의
    실제 필터링/집계 로직을 검증한다. 체크박스 상태에 따라 P 재고와 부자재/홍보물 재고를
    빼고 재계산하고, 홍보물랙처럼 집계 제외 로케이션은 별도로 처리해야 한다."""

    def test_p_location_excluded_when_available_only_checked(self):
        captured = {}

        def fake_original(product_name, inv_df):
            captured["inv_df"] = inv_df
            return []

        patched = _load_patched_product_groups(
            fake_original,
            session_state={lmb._AVAILABLE_ONLY_KEY: True, lmb._EXCLUDE_MATERIALS_KEY: False},
        )
        inv_df = pd.DataFrame([
            {"location": "A1-01", "qty": 5, "company": "NOH"},
            {"location": "P", "qty": 3, "company": "NOH"},
        ])
        patched("제품", inv_df)

        self.assertEqual(captured["inv_df"]["location"].tolist(), ["A1-01"])

    def test_p_location_kept_when_available_only_unchecked(self):
        captured = {}

        def fake_original(product_name, inv_df):
            captured["inv_df"] = inv_df
            return []

        patched = _load_patched_product_groups(
            fake_original,
            session_state={lmb._AVAILABLE_ONLY_KEY: False, lmb._EXCLUDE_MATERIALS_KEY: False},
        )
        inv_df = pd.DataFrame([
            {"location": "A1-01", "qty": 5, "company": "NOH"},
            {"location": "P", "qty": 3, "company": "NOH"},
        ])
        patched("제품", inv_df)

        self.assertEqual(sorted(captured["inv_df"]["location"].tolist()), ["A1-01", "P"])

    def test_material_locations_excluded_by_default(self):
        captured = {}

        def fake_original(product_name, inv_df):
            captured["inv_df"] = inv_df
            return []

        # 세션에 값이 없으면 부자재/홍보물 제외는 기본값 True로 동작해야 한다.
        patched = _load_patched_product_groups(fake_original, session_state={})
        inv_df = pd.DataFrame([
            {"location": "A1-01", "qty": 5, "company": "NOH"},
            {"location": "G1-01", "qty": 2, "company": "NOH"},
            {"location": "G2-01", "qty": 1, "company": "NOH"},
            {"location": "홍보물랙", "qty": 4, "company": "NOH"},
        ])
        patched("제품", inv_df)

        self.assertEqual(captured["inv_df"]["location"].tolist(), ["A1-01"])

    def test_material_locations_kept_when_unchecked(self):
        captured = {}

        def fake_original(product_name, inv_df):
            captured["inv_df"] = inv_df
            return []

        patched = _load_patched_product_groups(
            fake_original, session_state={lmb._EXCLUDE_MATERIALS_KEY: False}
        )
        inv_df = pd.DataFrame([
            {"location": "A1-01", "qty": 5, "company": "NOH"},
            {"location": "G1-01", "qty": 2, "company": "NOH"},
        ])
        patched("제품", inv_df)

        self.assertEqual(sorted(captured["inv_df"]["location"].tolist()), ["A1-01", "G1-01"])

    def test_product_master_material_is_excluded_outside_material_locations(self):
        captured = {}

        def fake_original(product_name, inv_df):
            captured["inv_df"] = inv_df
            return []

        patched = _load_patched_product_groups(
            fake_original,
            session_state={lmb._EXCLUDE_MATERIALS_KEY: True},
            material_products={"체크된 부자재"},
        )
        inv_df = pd.DataFrame([
            {"product_name": "체크된 부자재", "location": "A1-01", "qty": 5, "company": "NOH"},
            {"product_name": "일반 제품", "location": "B1-01", "qty": 3, "company": "NOH"},
        ])
        patched("제품", inv_df)

        self.assertEqual(captured["inv_df"]["product_name"].tolist(), ["일반 제품"])

    def test_empty_groups_are_dropped_when_materials_excluded(self):
        empty_rows = pd.DataFrame(columns=["location", "qty", "company"])
        patched = _load_patched_product_groups(
            lambda product_name, inv_df: [{"rows": empty_rows, "total_qty": 0}],
            session_state={lmb._EXCLUDE_MATERIALS_KEY: True},
        )
        groups = patched("제품", pd.DataFrame(columns=["location", "qty", "company"]))
        self.assertEqual(groups, [])

    def test_empty_groups_are_kept_when_materials_not_excluded(self):
        empty_rows = pd.DataFrame(columns=["location", "qty", "company"])
        patched = _load_patched_product_groups(
            lambda product_name, inv_df: [{"rows": empty_rows, "total_qty": 0}],
            session_state={lmb._EXCLUDE_MATERIALS_KEY: False},
        )
        groups = patched("제품", pd.DataFrame(columns=["location", "qty", "company"]))
        self.assertEqual(len(groups), 1)

    def test_non_counted_location_zeroed_and_excluded_from_total_qty(self):
        fixed_rows = pd.DataFrame([
            {"location": "A1-01", "qty": 5, "company": "NOH"},
            {"location": "홍보물랙", "qty": 100, "company": "NOH"},
        ])
        patched = _load_patched_product_groups(
            lambda product_name, inv_df: [{"rows": fixed_rows, "total_qty": 105}],
        )
        groups = patched("제품", fixed_rows)

        group = groups[0]
        self.assertEqual(group["total_qty"], 5)
        rows = group["rows"]
        self.assertEqual(rows["qty"].tolist(), [5, 0])
        self.assertTrue(rows["location"].iloc[1].startswith(lmb._SPECIAL_SORT_PREFIX))
        self.assertTrue(rows["company"].iloc[1].startswith(lmb._SPECIAL_SORT_PREFIX))
        # 집계 대상 행은 건드리지 않는다.
        self.assertEqual(rows["location"].iloc[0], "A1-01")
        self.assertEqual(rows["company"].iloc[0], "NOH")

    def test_group_without_non_counted_rows_is_left_unchanged(self):
        fixed_rows = pd.DataFrame([
            {"location": "A1-01", "qty": 5, "company": "NOH"},
        ])
        patched = _load_patched_product_groups(
            lambda product_name, inv_df: [{"rows": fixed_rows, "total_qty": 5}],
        )
        groups = patched("제품", fixed_rows)

        self.assertEqual(groups[0]["total_qty"], 5)
        self.assertEqual(groups[0]["rows"]["qty"].tolist(), [5])


if __name__ == "__main__":
    unittest.main()
