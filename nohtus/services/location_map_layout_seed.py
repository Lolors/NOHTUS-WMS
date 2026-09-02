from __future__ import annotations


def _i(code,x,y,w=70,h=56,company="기타",label=None,kind="location",note=""):
    return {"code":code,"label":label or code,"x":x,"y":y,"width":w,"height":h,"company":company,"kind":kind,"note":note}


def _rack(prefix,x,y,company,count=6,w=165,h=235):
    if prefix == "C1":
        cell_h = h / 3
        return [_i(f"C1-{n:02d}",x,round(y+(3-n)*cell_h),w,round(cell_h),company) for n in range(1,4)]
    order=[(3,0,0),(4,1,0),(2,0,1),(5,1,1),(1,0,2),(6,1,2)]
    cell_w = w / 2
    cell_h = h / 3
    return [_i(f"{prefix}-{n:02d}",round(x+c*cell_w),round(y+r*cell_h),round(cell_w),round(cell_h),company) for n,c,r in order if n<=count]


def initial_layout():
    items=[_i("G2",18,18,230,300,"기타",kind="zone",note="패키지 창고")]
    items += [_i(f"G1-0{n}",18+(n-1)*77,318,77,70) for n in range(1,4)]
    for p,x,c in [("A2",275,"노투스팜"),("B2",458,"노투스팜"),("C2",642,"노투스"),("D1",825,"노투스"),("E1",1008,"NOH")]: items += _rack(p,x,30,c)
    items += [_i(f"F1-0{n}",1190+(n-1)*75,30,75,78,"비자료") for n in range(1,4)] + [_i("X2",1422,30,60,78,"비자료",kind="zone")]
    items += _rack("A1",275,330,"노투스팜") + _rack("B1",458,330,"노투스팜") + _rack("C1",650,330,"노투스팜",3,83,235)
    items += [_i(f"X1-0{n}",1418,250+(n-1)*80,64,80,"비자료",note="폐기" if n>1 else "대표님 시술용 포함") for n in range(1,4)]
    items += [
        _i("P",18,600,160,82,"특수","P\n수출대기","zone"), _i("T1",190,600,105,82,"특수",kind="zone"),
        _i("Q",18,710,160,82,"특수","Q\n유통기한임박","zone"), _i("T2",190,710,105,82,"특수",kind="zone"),
        _i("REC",490,690,130,72,"특수","REC\nReceiving","zone","매입등록대기"), _i("다용도랙",18,830,290,62,"특수",kind="zone"),
        _i("R2",1280,615,92,72,"비자료","R2 비자료","zone"), _i("R1",1372,615,93,72,"기타","R1 자료","zone"),
        _i("N",1000,740,150,92,"기타","기타 위치","zone","오른쪽 창고 / 사무실(4층) / 지엠메딕 / 거래처 창고")]
    return {"version":1,"canvas":{"width":1482,"height":910,"grid":10},"items":items}
