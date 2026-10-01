"""Move reserved stock to another business without losing its export allocation."""
from contextlib import closing
from datetime import datetime
from nohtus.db import connect


def linked_move_orders(inventory_id):
    with closing(connect()) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='export_waiting_items'").fetchone():
            return []
        cur=con.execute("""SELECT o.id,o.export_no,o.country,o.buyer,SUM(i.qty) AS qty
            FROM export_waiting_items i JOIN export_waiting_orders o ON o.id=i.order_id
            WHERE i.waiting_inventory_id=? AND COALESCE(i.confirmed,0)=0
            AND o.status IN ('waiting','partial','confirmed')
            GROUP BY o.id ORDER BY o.id""",(int(inventory_id),))
        return [dict(zip([d[0] for d in cur.description],row)) for row in cur.fetchall()]


def _rows(cur,sql,args):
    cur.execute(sql,args)
    columns=[d[0] for d in cur.description]
    return [dict(zip(columns,row)) for row in cur.fetchall()]


def _insert(cur,table,row):
    values={k:v for k,v in row.items() if k!='id'}
    cur.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",tuple(values.values()))
    return cur.lastrowid


def move_linked_stock(src_id,to_company,to_location,qty,order_id,memo='',location_range_cells=None,*,company_correction=False):
    from nohtus.export_app.db import DB_PATH as EXPORT_DB_PATH
    from nohtus.services.inventory import insert_transaction_log, product_mapping_name_for
    from nohtus.services.export_waiting import STAGING_LOCATIONS
    import json
    qty=int(qty)
    if to_location not in STAGING_LOCATIONS:
        raise ValueError('연결된 수출대기 재고는 P 또는 T1~T5로 이동하세요.')
    now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if not EXPORT_DB_PATH.is_file():
        raise ValueError('수출 데이터베이스를 찾을 수 없습니다.')
    with closing(connect()) as con:
        con.execute('ATTACH DATABASE ? AS exports',(str(EXPORT_DB_PATH),))
        try:
            con.execute('BEGIN IMMEDIATE')
            cur=con.cursor()
            sources=_rows(cur,'SELECT * FROM inventory WHERE id=?',(int(src_id),))
            if not sources:raise ValueError('출발 재고를 찾을 수 없습니다.')
            source=sources[0]
            if to_company==source['company']:raise ValueError('사업장 변경 시에만 수출 주문을 선택하세요.')
            order=_rows(cur,"SELECT * FROM export_waiting_orders WHERE id=? AND status IN ('waiting','partial','confirmed')",(int(order_id),))
            items=_rows(cur,'SELECT * FROM export_waiting_items WHERE order_id=? AND waiting_inventory_id=? AND COALESCE(confirmed,0)=0 ORDER BY id',(int(order_id),int(src_id)))
            if not order or qty<=0 or qty>sum(int(i['qty']) for i in items) or qty>int(source['qty']):
                raise ValueError('선택한 주문의 연결 수량 또는 현재 재고를 초과했습니다. 다시 조회하세요.')
            if any(i['company']!=source['company'] or i['product_name']!=source['product_name'] for i in items):
                raise ValueError('수출대기 재고 연결이 일치하지 않습니다. 입고 수정에서 먼저 확인하세요.')
            cases=_rows(cur,'SELECT id FROM exports.export_cases WHERE TRIM(export_no)=TRIM(?)',(order[0]['export_no'],))
            if len(cases)>1:raise ValueError('동일 수출번호가 여러 주문에 연결되어 있어 이동할 수 없습니다.')
            warehouse=product_mapping_name_for(to_company,source['product_name']) or source['product_name']
            matches=_rows(cur,"SELECT * FROM inventory WHERE company=? AND product_name=? AND IFNULL(warehouse_name,'')=? AND lot=? AND exp_date=? AND location=?",(to_company,source['product_name'],warehouse,source['lot'],source['exp_date'],to_location))
            if len(matches)>1:raise ValueError('도착 재고가 중복되어 있습니다. 먼저 정리해 주세요.')
            if matches:
                dest_id=matches[0]['id']
                cur.execute('UPDATE inventory SET qty=qty+?,updated_at=? WHERE id=?',(qty,now,dest_id))
            else:
                dest=dict(source,company=to_company,warehouse_name=warehouse,location=to_location,qty=qty,updated_at=now)
                if 'location_range_cells' in dest:dest['location_range_cells']=json.dumps(location_range_cells or [],ensure_ascii=False)
                dest_id=_insert(cur,'inventory',dest)
            cur.execute('UPDATE inventory SET qty=qty-?,updated_at=? WHERE id=?',(qty,now,src_id))
            remaining=qty
            for item in items:
                if not remaining:break
                take=min(remaining,int(item['qty']))
                # New source identity is in the new business; cancelling leaves it there.
                changed=dict(item,company=to_company,warehouse_name=warehouse,source_inventory_id=dest_id,source_location=to_location,waiting_inventory_id=dest_id,waiting_location=to_location,qty=take,moved_at=now)
                if cases:
                    confirmed = cur.execute("SELECT COUNT(*) FROM export_waiting_items WHERE order_id=? AND source_inventory_id=? AND COALESCE(confirmed,0)=1",(order_id,item['source_inventory_id'])).fetchone()[0]
                    if confirmed:
                        raise ValueError('동일 출발재고에 확정 출고분이 함께 있어 자동 분리할 수 없습니다. 입고 수정에서 연결을 확인하세요.')
                    mirrors=_rows(cur,"""SELECT * FROM exports.shipment_items WHERE case_id=? AND source_inventory_id=?
                        AND business_unit=? AND product_name=? AND COALESCE(lot_no,'')=COALESCE(?,'')
                        AND COALESCE(expiry_date,'')=COALESCE(?,'') ORDER BY id""",(cases[0]['id'],item['source_inventory_id'],item['company'],item['product_name'],item['lot'],item['exp_date']))
                    if sum(float(m['requested_qty']) for m in mirrors)<take:
                        raise ValueError('수출 주문의 연결 수량이 일치하지 않아 이동을 취소했습니다. 입고 수정에서 확인하세요.')
                    left=take
                    for mirror in mirrors:
                        if left<=0:break
                        amount=min(left,float(mirror['requested_qty']))
                        change=dict(mirror,business_unit=to_company,location=to_location,source_inventory_id=dest_id,requested_qty=amount,updated_at=now)
                        if amount==float(mirror['requested_qty']):
                            cur.execute('UPDATE exports.shipment_items SET business_unit=?,location=?,source_inventory_id=?,updated_at=? WHERE id=?',(to_company,to_location,dest_id,now,mirror['id']))
                        else:
                            cur.execute('UPDATE exports.shipment_items SET requested_qty=requested_qty-?,updated_at=? WHERE id=?',(amount,now,mirror['id']))
                            _insert(cur,'exports.shipment_items',change)
                        left-=amount
                if take==int(item['qty']):
                    cur.execute('DELETE FROM export_waiting_items WHERE id=?',(item['id'],))
                else:cur.execute('UPDATE export_waiting_items SET qty=qty-? WHERE id=?',(take,item['id']))
                _insert(cur,'export_waiting_items',changed)
                remaining-=take
            cur.execute('UPDATE export_waiting_orders SET updated_at=? WHERE id=?',(now,order_id))
            if cases:cur.execute('UPDATE exports.export_cases SET updated_at=? WHERE id=?',(now,cases[0]['id']))
            insert_transaction_log(cur,created_at=now,tx_type='사업장정정' if company_correction else '사업장+위치이동',product_name=source['product_name'],warehouse_name=source.get('warehouse_name',''),lot=source['lot'],exp_date=source['exp_date'],from_company=source['company'],from_location=source['location'],to_company=to_company,to_location=to_location,qty=qty,memo=f"{memo} / 수출대기 주문 {order[0]['export_no']} 연결 이동")
            con.commit()
        except Exception:
            con.rollback()
            raise
