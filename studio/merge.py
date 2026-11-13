"""studio/raw/*.json (스튜디오 화면에서 받아 적은 표) → data/studio.json

    python studio/merge.py

raw 파일 이름: <채널 short>_<videos|daily|traffic|monet>.json  (short 는 channels.json)
- videos : 영상별 전체 기간 표
- daily  : 날짜별 최근 28일 표 (전에 받은 날짜는 지우지 않고 쌓는다)
- traffic: 유입 경로 최근 28일 표
- monet  : 수익 창출 조건 진행
받지 못한 채널·표는 이전 값을 그대로 둔다.
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(ROOT, "data", "studio.json")
MAX_AGE_H = 12          # 이보다 오래된 raw 파일은 '이번에 못 받은 것'으로 보고 합치지 않는다

COLS = {
    "조회수": "v", "유효 조회수": "ev", "시청 시간(단위: 시간)": "wh", "평균 시청 지속 시간": "awt",
    "평균 조회율": "avp", "계속 시청함": "stay", "구독자": "subs", "구독자 증가수": "sg", "구독자 감소수": "sl",
    "좋아요": "likes", "공유": "shares", "추가된 댓글 수": "cm", "썸네일 노출수": "imp", "썸네일 클릭률": "ctr",
}


def num(s):
    """'56,113' → 56113, '405.3' → 405.3, '73.3%' → 73.3, '0:45' → 45(초), '4.8만' → 48000, '—' → None"""
    s = (s or "").strip().replace(",", "").replace("회", "").replace("명", "").replace("시간", "")
    if s in ("", "—", "-", "–"):
        return None
    if re.fullmatch(r"\d+(:\d{1,2}){1,2}", s):
        sec = 0
        for part in s.split(":"):
            sec = sec * 60 + int(part)
        return sec
    mult = 1
    if s.endswith("%"):
        s = s[:-1]
    for unit, m in (("억", 1e8), ("만", 1e4), ("천", 1e3)):
        if s.endswith(unit):
            s, mult = s[:-1], m
    try:
        x = float(s) * mult
    except ValueError:
        return None
    return int(x) if x == int(x) and "." not in s else round(x, 2)


def day(s):
    m = re.search(r"(\d{4})\. ?(\d{1,2})\. ?(\d{1,2})", s or "")
    return "%04d-%02d-%02d" % tuple(int(x) for x in m.groups()) if m else None


def read(short, kind):
    p = os.path.join(RAW, f"{short}_{kind}.json")
    if not os.path.exists(p):
        return None
    age_h = (datetime.datetime.now().timestamp() - os.path.getmtime(p)) / 3600
    if age_h > MAX_AGE_H:
        print(f"  ! {short}_{kind}: {age_h:.0f}시간 전에 받은 파일이라 건너뜀(이번에 못 받음)")
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    if kind != "monet" and not d.get("rows"):
        print(f"  ! {short}_{kind}: 표가 비어 있음(권한 없음·화면 오류), 건너뜀")
        return None
    return d


def table(d):
    """(합계 줄 dict, [(이름, dict)]) — 열 이름은 COLS 로 바꾼다."""
    keys = [COLS[h] for h in d["heads"] if h in COLS]
    total, rows = None, []
    for r in d["rows"]:
        name, vals = r[0], r[1:]
        if len(vals) != len(keys):
            print(f"  ! {d.get('name')}: 열 수 다름({len(vals)}≠{len(keys)}) → 줄 건너뜀: {name}")
            continue
        rec = {k: num(v) for k, v in zip(keys, vals)}
        if name == "합계":
            total = rec
        else:
            rows.append((name, rec))
    return total, rows


def main():
    with open(os.path.join(ROOT, "channels.json"), encoding="utf-8") as f:
        chans = json.load(f)["channels"]
    out = {"channels": {}, "videos": {}}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            out = json.load(f)
    out.setdefault("channels", {})
    out.setdefault("videos", {})

    for c in chans:
        short, key = c.get("short"), c["handle"]
        if not short:
            continue
        ch = out["channels"].setdefault(key, {})
        got = []

        d = read(short, "videos")
        if d:
            total, rows = table(d)
            if d.get("more"):
                print(f"  ! {short}_videos: 다음 쪽이 더 있음(50개 넘음) — 첫 쪽만 반영")
            ch["total"] = total
            ch["through"] = day(d["range"].split("~")[-1])
            ch["read_at"] = d.get("read_at")
            for vid, rec in rows:
                rec["ch"] = key
                out["videos"][vid] = rec
            got.append(f"영상 {len(rows)}")

        d = read(short, "daily")
        if d:
            total, rows = table(d)
            ch["p28"] = total
            ch["p28_range"] = [day(x) for x in d["range"].split("~")]
            days = {x["d"]: x for x in ch.get("daily", [])}
            for name, rec in rows:
                dd = day(name)
                if dd:
                    rec["d"] = dd
                    days[dd] = rec
            ch["daily"] = [days[k] for k in sorted(days)]
            ch["read_at"] = d.get("read_at") or ch.get("read_at")
            got.append(f"날짜 {len(rows)}")

        d = read(short, "traffic")
        if d:
            total, rows = table(d)
            ch["traffic"] = [dict(rec, name=name) for name, rec in rows if rec.get("v")]
            got.append(f"유입 {len(rows)}")

        d = read(short, "monet")
        if d:
            ch["monet"] = {"as_of": day(d.get("as_of")), "subs": num(d.get("subs")), "watch_h": num(d.get("watch_h")),
                           "shorts": num(d.get("shorts")), "note": (d.get("note") or "").strip() or None}
            got.append("수익 조건")

        if not ch:
            del out["channels"][key]
        print(f"{c['name']}: {', '.join(got) if got else '받은 표 없음(이전 값 유지)'}")

    out["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("저장:", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
