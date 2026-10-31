"""경쟁 채널 신작·급등 감시 — fetch_stats.py 다음에 1시간마다 실행.
rivals.json 의 채널마다 최근 업로드 15개를 보고
- 평소 조회수(48시간 넘은 영상들의 중앙값)를 계산하고
- 최근 7일 영상의 조회수를 시간대별로 data/rivals.json 에 쌓는다.
"""
import datetime
import json
import os
import statistics

from fetch_stats import ROOT, api, iso_seconds, load, save

CFG = os.path.join(ROOT, "rivals.json")
OUT = os.path.join(ROOT, "data", "rivals.json")
TRACK_HOURS = 168   # 7일까지 추적
KEEP_DAYS = 14      # 기록 보관
SHORT_MAX = 180     # 3분 이하 = 쇼츠


def parse(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main():
    cfg = load(CFG, {"groups": [], "channels": []})
    db = load(OUT, {"channels": {}, "videos": {}})
    now = datetime.datetime.now(datetime.timezone.utc)
    chans = cfg["channels"]

    # 채널 이름·구독자 (50개씩 1단위)
    for i in range(0, len(chans), 50):
        part = chans[i:i + 50]
        res = api("channels", {"part": "snippet,statistics", "id": ",".join(c["id"] for c in part), "maxResults": 50})
        by_id = {it["id"]: it for it in res.get("items", [])}
        for c in part:
            it = by_id.get(c["id"])
            rec = db["channels"].setdefault(c["id"], {})
            rec["name"] = c.get("name") or (it["snippet"]["title"] if it else c["id"])
            rec["group"] = c["group"]
            if it:
                s = it["statistics"]
                rec["subs"] = None if s.get("hiddenSubscriberCount") else int(s.get("subscriberCount", 0))

    # 채널별 최근 업로드 15개
    owner = {}
    for c in chans:
        try:
            res = api("playlistItems", {"part": "contentDetails", "playlistId": "UU" + c["id"][2:], "maxResults": 15})
        except Exception as e:
            print("업로드 목록 실패:", c["name"], e)
            continue
        for it in res.get("items", []):
            owner[it["contentDetails"]["videoId"]] = c["id"]

    info = {}
    ids = list(owner)
    for i in range(0, len(ids), 50):
        res = api("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50])})
        for it in res.get("items", []):
            info[it["id"]] = it

    # 평소 조회수: 48시간 넘은 영상 중앙값 (쇼츠·롱폼 따로, 3개 미만이면 전체)
    for cid, rec in db["channels"].items():
        olds = []
        for vid, it in info.items():
            if owner[vid] != cid:
                continue
            age = (now - parse(it["snippet"]["publishedAt"])).total_seconds() / 3600
            if age >= 48:
                olds.append((iso_seconds(it["contentDetails"].get("duration")) <= SHORT_MAX,
                             int(it["statistics"].get("viewCount", 0))))
        everything = [v for _, v in olds]
        for key, is_short in (("base_s", True), ("base_l", False)):
            same = [v for s, v in olds if s == is_short]
            pick = same if len(same) >= 3 else everything
            rec[key] = int(statistics.median(pick)) if pick else None

    # 최근 7일 영상 기록
    cut = now - datetime.timedelta(hours=TRACK_HOURS)
    n = 0
    for vid, it in info.items():
        pub = parse(it["snippet"]["publishedAt"])
        if pub < cut:
            continue
        rec = db["videos"].setdefault(vid, {"c": owner[vid], "p": it["snippet"]["publishedAt"], "pts": []})
        rec["t"] = it["snippet"]["title"]
        rec["sec"] = iso_seconds(it["contentDetails"].get("duration"))
        rec["pts"].append([round((now - pub).total_seconds() / 3600, 2), int(it["statistics"].get("viewCount", 0))])
        n += 1

    vcut = now - datetime.timedelta(days=KEEP_DAYS)
    db["videos"] = {k: v for k, v in db["videos"].items() if parse(v["p"]) >= vcut}
    keep = {c["id"] for c in chans}
    db["channels"] = {k: v for k, v in db["channels"].items() if k in keep}
    db["groups"] = cfg["groups"]
    db["updated"] = now.isoformat(timespec="seconds")
    save(OUT, db)
    print("경쟁 채널:", len(chans), "개 / 최근 7일 영상:", n, "개")


if __name__ == "__main__":
    main()
