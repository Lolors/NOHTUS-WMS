from __future__ import annotations


def _i(code,x,y,w=70,h=56,company="기타",label=None,kind="location",note=""):
    return {"code":code,"label":label or code,"x":x,"y":y,"width":w,"height":h,"company":company,"kind":kind,"note":note}


def _rack(prefix,x,y,company,count=6):
    if prefix == "C1":
        return [_i(f"C1-{n:02d}",x,y+(3-n)*58,142,56,company) for n in range(1,4)]
    order=[(3,0,0),(4,1,0),(2,0,1),(5,1,1),(1,0,2),(6,1,2)]
    return [_i(f"{prefix}-{n:02d}",x+c*72,y+r*58,70,56,company) for n,c,r in order if n<=count]


def initial_layout():
    items=[_i("G2",20,40,210,180,"기타",kind="zone",note="패키지 창고")]
    items += [_i(f"G1-0{n}",20+(n-1)*70,230,68,54) for n in range(1,4)]
    for p,x,c in [("A2",280,"노투스팜"),("B2",450,"노투스팜"),("C2",620,"노투스"),("D1",790,"노투스"),("E1",960,"NOH")]: items += _rack(p,x,40,c)
    items += [_i(f"F1-0{n}",1135,40+(n-1)*58,70,56,"비자료") for n in range(1,4)] + [_i("X2",1210,40,50,56,kind="zone")]
    items += _rack("A1",280,330,"노투스팜") + _rack("B1",450,330,"노투스팜") + _rack("C1",620,330,"노투스팜",3)
    items += [_i(f"X1-0{n}",1135,330+(n-1)*58,70,56,note="폐기" if n>1 else "대표님 시술용 포함") for n in range(1,4)]
    items += [
        _i("P",40,610,150,60,"특수","P 수출대기","zone"), _i("T1",230,610,100,60,"특수",kind="zone"),
        _i("T2",230,690,100,60,"특수",kind="zone"), _i("Q",40,690,150,60,"특수","Q 유통기간임박","zone"),
        _i("REC",470,650,180,70,"특수","REC Receiving","zone","매입등록대기"), _i("홍보물랙",40,790,290,70,"특수",kind="zone"),
        _i("R2",1060,650,90,60,"비자료","R2 비자료","zone"), _i("R1",1155,650,90,60,"기타","R1 자료","zone"),
        _i("N",1060,760,185,80,"기타","기타 위치","zone","회색 카트 / 오른쪽 창고 / 사무실(4층)")]
    return {"version":1,"canvas":{"width":1280,"height":900,"grid":10},"items":items}
