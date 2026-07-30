from __future__ import annotations


def resolve_customer_last_sale_date(customer_name, company, exact_map, name_map):
    """사업장이 있으면 반드시 거래처명+사업장 조합의 최근거래일만 반환한다."""
    customer = str(customer_name or "").strip()
    company = str(company or "").strip()
    if company:
        return str(exact_map.get((customer, company), "") or "").strip()
    return str(name_map.get(customer, "") or "").strip()
