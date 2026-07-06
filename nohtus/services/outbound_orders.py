"""Outbound order save/update wrapper services.

The heavy DB save/update implementation still lives in app.py for now.
This wrapper removes direct app.py imports from page modules first, then the
implementation can be migrated here in smaller safe commits.
"""
from __future__ import annotations
import streamlit as st
from nohtus.services.inventory import insert_transaction_log
from nohtus.dates import display_date_only
from nohtus.db import connect
from datetime import datetime

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
    missing_id = [item for item in valid_cart if not item.get('id')]
    if missing_id:
        names = ', '.join(sorted({str(x.get('제품명') or '-') for x in missing_id}))
        raise ValueError(f'재고ID가 없는 장바구니 행이 있어 출고지시를 저장할 수 없습니다: {names}')
    inv_ids = sorted({int(item.get('id')) for item in valid_cart})
    requested_by_inv = {}
    for item in valid_cart:
        inv_key = int(item.get('id'))
        requested_by_inv[inv_key] = requested_by_inv.get(inv_key, 0) + int(item.get('요청수량', 0) or 0)
    with connect() as con:
        cur = con.cursor()
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
        cur.execute('INSERT INTO outbound_orders(created_at, order_date, title, status, memo) VALUES(?,?,?,?,?)', (now, order_date, title or f'출고지시 {now}', '저장됨', memo))
        order_id = cur.lastrowid
        final_by_inv = {}
        for inv_key, req_qty in requested_by_inv.items():
            before_qty = int(inv_map[inv_key].get('qty', 0) or 0)
            final_stock = before_qty - int(req_qty)
            cur.execute('UPDATE inventory SET qty=?, updated_at=? WHERE id=?', (final_stock, now, inv_key))
            final_by_inv[inv_key] = final_stock
        running_final = {k: int(inv_map[k].get('qty', 0) or 0) for k in inv_map}
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
            insert_transaction_log(cur, created_at=now, tx_type='출고지시', product_name=product, warehouse_name=wh, lot=lot, exp_date=exp, from_company=company, from_location=loc, to_company=None, to_location=None, qty=qty, memo=f'출고지시서 #{order_id} / 재고차감')
        con.commit()
        return order_id

def update_outbound_order(order_id, title_or_cart, maybe_cart=None):
    """저장된 출고지시서를 수정한다.
    기존 호출 호환: update_outbound_order(id, cart) 또는 update_outbound_order(id, title, cart).

    운영 기준:
    - 저장된 출고지시는 이미 inventory에서 차감된 상태다.
    - 수정 저장 시 기존 지시 수량을 먼저 원복한 뒤 새 장바구니 수량을 다시 차감한다.
    - 제조번호/유통기한/로케이션까지 같은 inventory_id 기준으로만 처리한다.
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
    missing_id = [item for item in valid_cart if not item.get('id')]
    if missing_id:
        names = ', '.join(sorted({str(x.get('제품명') or '-') for x in missing_id}))
        raise ValueError(f'재고ID가 없는 장바구니 행이 있어 출고지시를 수정할 수 없습니다: {names}')
    new_requested_by_inv = {}
    for item in valid_cart:
        inv_key = int(item.get('id'))
        new_requested_by_inv[inv_key] = new_requested_by_inv.get(inv_key, 0) + int(item.get('요청수량', 0) or 0)
    with connect() as con:
        cur = con.cursor()
        order = cur.execute('SELECT id, status FROM outbound_orders WHERE id=?', (order_id,)).fetchone()
        if not order:
            raise ValueError('수정할 출고지시서를 찾을 수 없습니다.')
        if str(order[1] or '') == '취소됨':
            raise ValueError('취소된 출고지시서는 수정할 수 없습니다.')
        old_rows = cur.execute('SELECT inventory_id, location, product_name, lot, exp_date, qty, company, warehouse_name\n                                  FROM outbound_order_items WHERE order_id=? ORDER BY id', (order_id,)).fetchall()
        old_by_inv = {}
        for inv_id, location, product_name, lot, exp_date, qty, company, warehouse_name in old_rows:
            if inv_id:
                old_by_inv[int(inv_id)] = old_by_inv.get(int(inv_id), 0) + int(qty or 0)
        all_inv_ids = sorted(set(old_by_inv.keys()) | set(new_requested_by_inv.keys()))
        if not all_inv_ids:
            raise ValueError('수정할 재고행을 찾을 수 없습니다.')
        placeholders = ','.join(['?'] * len(all_inv_ids))
        rows = cur.execute(f'SELECT * FROM inventory WHERE id IN ({placeholders})', all_inv_ids).fetchall()
        cols = [d[0] for d in cur.description]
        inv_map = {int(row[cols.index('id')]): dict(zip(cols, row)) for row in rows}
        for inv_key, new_qty in new_requested_by_inv.items():
            src = inv_map.get(inv_key)
            if not src:
                raise ValueError(f'현재고 DB에서 찾을 수 없는 재고ID가 있습니다: {inv_key}')
            available_after_restore = int(src.get('qty', 0) or 0) + int(old_by_inv.get(inv_key, 0) or 0)
            if new_qty > available_after_restore:
                product = src.get('product_name', '-')
                loc = src.get('location', '-')
                lot = src.get('lot', '-')
                exp = display_date_only(src.get('exp_date', '-'))
                raise ValueError(f'{product} / {loc} / {lot} / {exp} 재고가 부족합니다. 원복 후 가능 {available_after_restore}EA, 요청 {new_qty}EA')
        for inv_key, old_qty in old_by_inv.items():
            src = inv_map.get(inv_key)
            if src:
                restored = int(src.get('qty', 0) or 0) + int(old_qty or 0)
                cur.execute('UPDATE inventory SET qty=?, updated_at=? WHERE id=?', (restored, now, inv_key))
                src['qty'] = restored
        cur.execute('DELETE FROM outbound_order_items WHERE order_id=?', (order_id,))
        final_by_inv = {}
        for inv_key, new_qty in new_requested_by_inv.items():
            src = inv_map[inv_key]
            final_stock = int(src.get('qty', 0) or 0) - int(new_qty or 0)
            cur.execute('UPDATE inventory SET qty=?, updated_at=? WHERE id=?', (final_stock, now, inv_key))
            final_by_inv[inv_key] = final_stock
        running_final = {k: int(inv_map[k].get('qty', 0) or 0) for k in inv_map}
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
            insert_transaction_log(cur, created_at=now, tx_type='출고지시수정', product_name=product, warehouse_name=wh, lot=lot, exp_date=exp, from_company=company, from_location=loc, to_company=None, to_location=None, qty=qty, memo=f'출고지시서 #{order_id} 수정 / 재고 재차감')
        if title is not None:
            cur.execute("UPDATE outbound_orders SET title=?, status='수정됨', memo=IFNULL(memo,'') || ? WHERE id=?", (title or f'출고지시서 #{order_id}', '\n' + now + ' 수정', order_id))
        else:
            cur.execute("UPDATE outbound_orders SET status='수정됨', memo=IFNULL(memo,'') || ? WHERE id=?", ('\n' + now + ' 수정', order_id))
        con.commit()
