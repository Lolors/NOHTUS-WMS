import ast
from pathlib import Path


SOURCE_PATH = Path(__file__).parents[1] / "nohtus" / "pages" / "own_product_status.py"


def _product_lists():
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    namespace = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name)
            and target.id in {"OWN_PRODUCTS", "OWN_PRODUCTS_BY_COMPANY"}
            for target in node.targets
        ):
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE_PATH), "exec"), {}, namespace)
    return namespace["OWN_PRODUCTS_BY_COMPANY"]


def test_highby_is_listed_only_for_nohtus_after_myclear():
    products_by_company = _product_lists()

    assert "하이바이 (5EA)" not in products_by_company["노투스팜"]
    assert "하이바이 (5EA)" not in products_by_company["NOH"]
    assert products_by_company["노투스"][-2:] == [
        "마이클리어 (10 EA)",
        "하이바이 (5EA)",
    ]
