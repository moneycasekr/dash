"""유튜브 채널 통계 수집 — GitHub Actions가 1시간마다 실행.
channels.json 의 채널을 조회해 data/history.json 에 기록을 쌓는다.
"""
import datetime
import json
import os
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(ROOT, "channels.json")
OUT = os.path.join(ROOT, "data", "history.json")
KEEP_DAYS = 30
KEY = os.environ["YT_API_KEY"]


def api(params):
    params = dict(params, key=KEY)
    url = "https://www.googleapis.com/youtube/v3/channels?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main():
    cfg = json.load(open(CFG, encoding="utf-8"))
    if os.path.exists(OUT):
        hist = json.load(open(OUT, encoding="utf-8"))
    else:
        hist = {"ids": {}, "snapshots": []}

    # @핸들 → 채널 ID (한 번만 조회 후 저장)
    for ch in cfg["channels"]:
        k = ch["handle"]
        if ch.get("id"):
            hist["ids"][k] = ch["id"]
        elif k not in hist["ids"]:
            res = api({"part": "id", "forHandle": k})
            items = res.get("items") or []
            if items:
                hist["ids"][k] = items[0]["id"]
            else:
                print("채널을 찾지 못함:", k)

    ids = [hist["ids"][c["handle"]] for c in cfg["channels"] if c["handle"] in hist["ids"]]
    stats, titles = {}, {}
    if ids:
        res = api({"part": "snippet,statistics", "id": ",".join(ids), "maxResults": 50})
        by_id = {it["id"]: it for it in res.get("items", [])}
        for c in cfg["channels"]:
            it = by_id.get(hist["ids"].get(c["handle"]))
            if not it:
                continue
            s = it["statistics"]
            stats[c["handle"]] = {
                "v": int(s.get("viewCount", 0)),
                "s": None if s.get("hiddenSubscriberCount") else int(s.get("subscriberCount", 0)),
                "n": int(s.get("videoCount", 0)),
            }
            titles[c["handle"]] = it["snippet"]["title"]

    now = datetime.datetime.now(datetime.timezone.utc)
    hist["snapshots"].append({"t": now.isoformat(timespec="seconds"), "c": stats})
    cut = now - datetime.timedelta(days=KEEP_DAYS)
    hist["snapshots"] = [
        s for s in hist["snapshots"] if datetime.datetime.fromisoformat(s["t"]) >= cut
    ]
    hist["channels"] = [
        {"handle": c["handle"], "name": c.get("name") or titles.get(c["handle"], c["handle"]), "color": c["color"]}
        for c in cfg["channels"]
    ]
    hist["updated"] = now.isoformat(timespec="seconds")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(hist, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("저장:", len(stats), "개 채널")


if __name__ == "__main__":
    main()
