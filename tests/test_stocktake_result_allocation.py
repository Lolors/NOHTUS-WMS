import pandas as pd

from nohtus.pages.stocktake import _allocate_erp_quantity_by_detail


def test_allocates_small_expiry_exactly_and_remainder_to_largest():
    actual = pd.Series([1200, 1], index=[10, 11])

    allocated = _allocate_erp_quantity_by_detail(actual, 3764)

    assert allocated.to_dict() == {10: 3763, 11: 1}
    assert (actual - allocated).to_dict() == {10: -2563, 11: 0}
    assert allocated.sum() == 3764


def test_preserves_original_indexes_when_actual_quantities_are_unsorted():
    actual = pd.Series([50, 2, 10], index=[7, 3, 9])

    allocated = _allocate_erp_quantity_by_detail(actual, 100)

    assert allocated.to_dict() == {7: 88, 3: 2, 9: 10}
    assert allocated.sum() == 100
