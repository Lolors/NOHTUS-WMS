"""Outbound order save/update wrapper services.

The heavy DB save/update implementation still lives in app.py for now.
This wrapper removes direct app.py imports from page modules first, then the
implementation can be migrated here in smaller safe commits.
"""
from __future__ import annotations
import streamlit as st
from nohtus.services.inventory import insert_transaction_log, stock_key_final_qty
from nohtus.dates import display_date_only
from nohtus.db import connect
from datetime import datetime


OUTBOUND_REDEDUCT_TX_TYPE = '출고지시 재차감'
TITLE_EDIT_TX_TYPE = '출고지시 제목수정'


def _norm(value):
    return str(value or '').strip()


def _norm_blank(value):
    value = _norm(value)
    return '' if value == '-' else value


def _norm_date(value):
    value = _norm(value)
    if not value or value == '-':
        return ''
    shown = _norm(display_date_only(value))
    return '' if shown == '-' else shown


def _first_value(item, *keys):
    for key in keys:
        value = item.get(key)
        if _norm(value):
            return value
    return ''


def _stock_key(company, product_name, lot, exp_date):
    return (
        _norm(company),
        _norm(product_name),
        _norm(lot) or '-',
        _norm(exp_date) or '-',
    )


def _inventory_match_payload(item):
    return {
        'product_name': _first_value(item, '제품명', 'product_name'),
        'company': _first_value(item, '사업장', '사업체', 'company'),
        'location': _first_value(item, '로케이션', 'location'),
        'lot': _first_value(item, 'LOT', 'lot'),
        'exp_date': _first_value(item, '유통기한', 'exp_date'),
        'warehouse_name': _first_value(item, '전산상 명칭', 'warehouse_name'),
    }


def _resolve_inventory_id(cur, item):
    """장바구니/저장행의 재고ID가 빠졌을 때 재고 고유 조건으로 inventory.id를 복구한다."""
    payload = _inventory_match_payload(item)
    product = _norm(payload['product_name'])
    company = _norm(payload['company'])
    location = _norm(payload['location'])
    lot = _norm_blank(payload['lot'])
    exp = _norm_date(payload['exp_date'])
    wh = _norm(payload['warehouse_name'])

    if not product or not company or not location:
        return None

    rows = cur.execute(
        """
        SELECT *
        FROM inventory
        WHERE TRIM(COALESCE(product_name,''))=?
          AND TRIM(COALESCE(company,''))=?
          AND TRIM(COALESCE(location,''))=?
        ORDER BY id DESC
        """,
        (product, company, location),
    ).fetchall()
    if not rows:
        return None

    cols = [d[0] for d in cur.description]
    candidates = []
    for row in rows:
        src = dict(zip(cols, row))
        if lot and _norm_blank(src.get('lot')) != lot:
            continue
        if exp and _norm_date(src.get('exp_date')) != exp:
            continue
        candidates.append(src)

    if not candidates:
        return None

    if wh:
        wh_matches = [src for src in candidates if _norm(src.get('warehouse_name')) == wh]
        if wh_matches:
            candidates = wh_matches

    # 같은 조건의 중복 행이 있어도 재고 수정이 멈추지 않도록 최신 inventory row를 사용한다.
    candidates = sorted(candidates, key=lambda src: int(src.get('id') or 0), reverse=True)
    return int(candidates[0]['id'])


def _resolve_cart_inventory_ids(cur, cart, *, action_label):
    resolved = []
    missing = []
    for item in cart or []:
        fixed = dict(item)
        raw_id = fixed.get('id') or fixed.get('inventory_id')
        inv_id = None
        if raw_id:
            try:
                inv_id = int(raw_id)
            except Exception:
                inv_id = None
            if inv_id:
                exists = cur.execute('SELECT id FROM inventory WHERE id=?', (inv_id,)).fetchone()
                if not exists:
                    inv_id = None
        if not inv_id:
            inv_id = _resolve_inventory_id(cur, fixed)
        if not inv_id:
            missing.append(fixed)
            continue
        fixed['id'] = inv_id
        fixed['inventory_id'] = inv_id
        resolved.append(fixed)

    if missing:
        names = ', '.join(sorted({
            str(_first_value(x, '제품명', 'product_name') or '-')
            for x in missing
        }))
        raise ValueError(f'재고DB에는 제품이 있을 수 있지만, 사업장/로케이션/LOT/유통기한까지 일치하는 재고행을 찾지 못해 출고지시를 {action_label}할 수 없습니다: {names}')
    return resolved


def _init_running_final(cur, running_final, src):
    key = _stock_key(src.get('company'), src.get('product_name'), src.get('lot'), src.get('exp_date'))
    if key not in running_final:
        running_final[key] = stock_key_final_qty(
            cur,
            company=src.get('company'),
            product_name=src.get('product_name'),
            lot=src.get('lot'),
            exp_date=src.get('exp_date'),
        ) or 0
    return key


def _requested_by_inventory(cart):
    result = {}
    for item in cart or []:
        inv_key = int(item.get('id'))
        result[inv_key] = result.get(inv_key, 0) + int(item.get('요청수량', 0) or 0)
    return result


def save_outbound_order(cart, title='', memo=''):
    """장바구니를 출고지시서로 저장한다.
    출고지시 저장 시점에 inventory 현재고를 즉시 차감한다.
    같은 inventory_id가 장바구니에 여러 번 들어와도 합산 검증 후 차감하여 중복 출고를 막는다.
    """
    if not cart:
        raise ValueError('저장할 출고지시 품목이 없습니다.')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    order_date = datetime.now().strftime('%Y-%m-%d')
    valid_cart = [item for item in cart or [] if int(item.get('요청수량', 0) or 0) > 0]
    if not valid_cart:
        raise ValueError('저장할 출고지시 품목이 없습니다.')
    with connect() as con:
        cur = con.cursor()
        valid_cart = _resolve_cart_inventory_ids(cur, valid_cart, action_label='저장')
        inv_ids = sorted({int(item.get('id')) for item in valid_cart})
        requested_by_inv = _requested_by_inventory(valid_cart)
        placeholders = ','.join(['?'] * len(inv_ids))
        rows = cur.execute(f'SELECT * FROM inventory WHERE id IN ({placeholders})', inv_ids).fetchall()
        cols = [d[0] for d in cur.description]
        inv_map = {int(row[cols.index('id')]): dict(zip(cols, row)) for row in rows}
        missing = [x for x in inv_ids if x not in inv_map]
        if missing:
            raise ValueError(f'현재고 DB에서 찾을 수 없는 재고ID가 있습니다: {missing}')
        for inv_key, req_qty in requested_by_inv.items():
            src = inv_map[inv_key]
            before_qty = int(src.get('qty', 0) or 0)
            if req_qty <= 0:
                raise ValueError('출고 요청 수량이 올바르지 않습니다.')
            if req_qty > before_qty:
                product = src.get('product_name', '-')
                loc = src.get('location', '-')
                lot = src.get('lot', '-')
                exp = display_date_only(src.get('exp_date', '-'))
                raise ValueError(f'{product} / {loc} / {lot} / {exp} 재고가 부족합니다. 현재 {before_qty}EA, 요청 {req_qty}EA')
        running_final = {}
        for inv_key in requested_by_inv:
            _init_running_final(cur, running_final, inv_map[inv_key])
        cur.execute('INSERT INTO outbound_orders(created_at, order_date, title, status, memo) VALUES(?,?,?,?,?)', (now, order_date, title or f'출고지시 {now}', '저장됨', memo))
        order_id = cur.lastrowid
        for inv_key, req_qty in requested_by_inv.items():
            before_qty = int(inv_map[inv_key].get('qty', 0) or 0)
            final_stock = before_qty - int(req_qty)
            cur.execute('UPDATE inventory SET qty=?, updated_at=? WHERE id=?', (final_stock, now, inv_key))
        for item in valid_cart:
            qty = int(item.get('요청수량', 0) or 0)
            inv_key = int(item.get('id'))
            src = inv_map[inv_key]
            company = src.get('company', item.get('사업장', item.get('사업체', '')))
            wh = src.get('warehouse_name', item.get('전산상 명칭', item.get('warehouse_name', '')))
            loc = src.get('location', item.get('로케이션', ''))
            product = src.get('product_name', item.get('제품명', ''))
            lot = src.get('lot', item.get('LOT', '-'))
            exp = src.get('exp_date', item.get('유통기한', '-'))
            cur.execute('INSERT INTO outbound_order_items(order_id, inventory_id, location, product_name, lot, exp_date, qty, company, warehouse_name)\n                           VALUES(?,?,?,?,?,?,?,?,?)', (order_id, inv_key, loc, product, lot, exp, qty, company, wh))
            key = _stock_key(company, product, lot, exp)
            running_final[key] = int(running_final.get(key, 0) or 0) - qty
            insert_transaction_log(cur, created_at=now, tx_type='출고지시', product_name=product, warehouse_name=wh, lot=lot, exp_date=exp, from_company=company, from_location=loc, to_company=None, to_location=None, qty=qty, memo=f'출고지시서 #{order_id} / 재고차감', final_stock=running_final[key])
        con.commit()
        return order_id


def update_outbound_order(order_id, title_or_cart, maybe_cart=None):
    """저장된 출고지시서를 수정한다.
    기존 호출 호환: update_outbound_order(id, cart) 또는 update_outbound_order(id, title, cart).

    운영 기준:
    - 저장된 출고지시는 이미 inventory에서 차감된 상태다.
    - 수정 저장 시 기존 지시와 새 장바구니의 차이만 재고에 반영한다.
    - 이력도 변경된 품목/수량만 '출고지시 재차감'으로 남긴다.
    - 제목만 바뀐 경우 재고 이력 없이 제목 수정 이력만 남긴다.
    """
    if maybe_cart is None:
        title = None
        cart = title_or_cart
    else:
        title = title_or_cart
        cart = maybe_cart
    order_id = int(order_id)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    valid_cart = [item for item in cart or [] if int(item.get('요청수량', 0) or 0) > 0]
    if not valid_cart:
        raise ValueError('저장할 출고지시 품목이 없습니다.')

    with connect() as con:
        cur = con.cursor()
        order = cur.execute("SELECT id, status, COALESCE(title, '') AS title FROM outbound_orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise ValueError('수정할 출고지시서를 찾을 수 없습니다.')
        if str(order[1] or '') == '취소됨':
            raise ValueError('취소된 출고지시서는 수정할 수 없습니다.')
        old_title = str(order[2] or '').strip()
        new_title = str(title if title is not None else old_title).strip() or f'출고지시서 #{order_id}'
        title_changed = title is not None and old_title != new_title

        valid_cart = _resolve_cart_inventory_ids(cur, valid_cart, action_label='수정')
        new_requested_by_inv = _requested_by_inventory(valid_cart)

        old_rows = cur.execute('SELECT inventory_id, location, product_name, lot, exp_date, qty, company, warehouse_name\n                                  FROM outbound_order_items WHERE order_id=? ORDER BY id', (order_id,)).fetchall()
        old_by_inv = {}
        unresolved_old = []
        for inv_id, location, product_name, lot, exp_date, qty, company, warehouse_name in old_rows:
            old_item = {
                'inventory_id': inv_id,
                'id': inv_id,
                'location': location,
                'product_name': product_name,
                'lot': lot,
                'exp_date': exp_date,
                'company': company,
                'warehouse_name': warehouse_name,
            }
            resolved_inv_id = None
            if inv_id:
                try:
                    resolved_inv_id = int(inv_id)
                except Exception:
                    resolved_inv_id = None
                if resolved_inv_id:
                    exists = cur.execute('SELECT id FROM inventory WHERE id=?', (resolved_inv_id,)).fetchone()
                    if not exists:
                        resolved_inv_id = None
            if not resolved_inv_id:
                resolved_inv_id = _resolve_inventory_id(cur, old_item)
            if resolved_inv_id:
                old_by_inv[int(resolved_inv_id)] = old_by_inv.get(int(resolved_inv_id), 0) + int(qty or 0)
            else:
                unresolved_old.append(old_item)

        if unresolved_old:
            names = ', '.join(sorted({str(x.get('product_name') or '-') for x in unresolved_old}))
            raise ValueError(f'기존 출고지시의 재고행을 재고DB와 다시 연결하지 못했습니다: {names}')

        all_inv_ids = sorted(set(old_by_inv.keys()) | set(new_requested_by_inv.keys()))
        if not all_inv_ids:
            raise ValueError('수정할 재고행을 찾을 수 없습니다.')
        placeholders = ','.join(['?'] * len(all_inv_ids))
        rows = cur.execute(f'SELECT * FROM inventory WHERE id IN ({placeholders})', all_inv_ids).fetchall()
        cols = [d[0] for d in cur.description]
        inv_map = {int(row[cols.index('id')]): dict(zip(cols, row)) for row in rows}
        missing_after_resolve = [x for x in all_inv_ids if x not in inv_map]
        if missing_after_resolve:
            raise ValueError(f'현재고 DB에서 찾을 수 없는 재고ID가 있습니다: {missing_after_resolve}')

        changed_deltas = {}
        for inv_key in all_inv_ids:
            old_qty = int(old_by_inv.get(inv_key, 0) or 0)
            new_qty = int(new_requested_by_inv.get(inv_key, 0) or 0)
            delta = new_qty - old_qty
            if delta:
                changed_deltas[inv_key] = delta

        for inv_key, delta in changed_deltas.items():
            src = inv_map.get(inv_key)
            if not src:
                raise ValueError(f'현재고 DB에서 찾을 수 없는 재고ID가 있습니다: {inv_key}')
            before_qty = int(src.get('qty', 0) or 0)
            after_qty = before_qty - int(delta)
            if after_qty < 0:
                product = src.get('product_name', '-')
                loc = src.get('location', '-')
                lot = src.get('lot', '-')
                exp = display_date_only(src.get('exp_date', '-'))
                raise ValueError(f'{product} / {loc} / {lot} / {exp} 재고가 부족합니다. 현재 {before_qty}EA, 추가 요청 {delta}EA')
            cur.execute('UPDATE inventory SET qty=?, updated_at=? WHERE id=?', (after_qty, now, inv_key))
            src['qty'] = after_qty

            company = src.get('company', '')
            wh = src.get('warehouse_name', '')
            loc = src.get('location', '')
            product = src.get('product_name', '')
            lot = src.get('lot', '-')
            exp = src.get('exp_date', '-')
            final_stock = stock_key_final_qty(cur, company=company, product_name=product, lot=lot, exp_date=exp)
            if delta > 0:
                change_desc = f'수량 증가 / 추가 재차감 {delta}EA'
            else:
                change_desc = f'수량 감소 또는 품목 제거 / {-delta}EA 원복'
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type=OUTBOUND_REDEDUCT_TX_TYPE,
                product_name=product,
                warehouse_name=wh,
                lot=lot,
                exp_date=exp,
                from_company=company,
                from_location=loc,
                to_company=None,
                to_location=None,
                qty=delta,
                memo=f'출고지시서 #{order_id} 수정 / {change_desc}',
                final_stock=final_stock,
            )

        if changed_deltas:
            cur.execute('DELETE FROM outbound_order_items WHERE order_id=?', (order_id,))
            for item in valid_cart:
                qty = int(item.get('요청수량', 0) or 0)
                inv_key = int(item.get('id'))
                src = inv_map[inv_key]
                company = src.get('company', item.get('사업장', ''))
                wh = src.get('warehouse_name', item.get('전산상 명칭', ''))
                loc = src.get('location', item.get('로케이션', ''))
                product = src.get('product_name', item.get('제품명', ''))
                lot = src.get('lot', item.get('LOT', '-'))
                exp = src.get('exp_date', item.get('유통기한', '-'))
                cur.execute('INSERT INTO outbound_order_items(order_id, inventory_id, location, product_name, lot, exp_date, qty, company, warehouse_name)\n                           VALUES(?,?,?,?,?,?,?,?,?)', (order_id, inv_key, loc, product, lot, exp, qty, company, wh))

        memo_parts = []
        if title_changed:
            insert_transaction_log(
                cur,
                created_at=now,
                tx_type=TITLE_EDIT_TX_TYPE,
                product_name='출고지시서 제목',
                warehouse_name=None,
                lot=None,
                exp_date=None,
                from_company=None,
                from_location=None,
                to_company=None,
                to_location=None,
                qty=0,
                memo=f"출고지시서 #{order_id} 제목 수정: '{old_title}' → '{new_title}'",
                final_stock=None,
            )
            memo_parts.append('제목 수정')
        if changed_deltas:
            memo_parts.append('품목/수량 수정')

        if title is not None:
            cur.execute("UPDATE outbound_orders SET title=?, status='수정됨', memo=IFNULL(memo,'') || ? WHERE id=?", (new_title, '\n' + now + ' ' + (' / '.join(memo_parts) or '수정'), order_id))
        else:
            cur.execute("UPDATE outbound_orders SET status='수정됨', memo=IFNULL(memo,'') || ? WHERE id=?", ('\n' + now + ' ' + (' / '.join(memo_parts) or '수정'), order_id))
        con.commit()
