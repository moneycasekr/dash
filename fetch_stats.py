"""유튜브 채널 통계 수집 — GitHub Actions가 1시간마다 실행.
- data/history.json : 채널 전체 숫자 (조회·구독·영상 수)
- data/videos.json  : 영상별 업로드 후 시간대별 조회수 (초반 성장 곡선)
"""
import datetime
import json
import os
import re
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(ROOT, "channels.json")
OUT = os.path.join(ROOT, "data", "history.json")
VOUT = os.path.join(ROOT, "data", "videos.json")
KEEP_DAYS = 30          # 채널 기록 보관
TRACK_HOURS = 168       # 영상은 업로드 후 7일까지 매시간 기록
VKEEP_DAYS = 90         # 영상 기록 보관
KEY = os.environ["YT_API_KEY"]


def api(endpoint, params):
    params = dict(params, key=KEY)
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def iso_seconds(dur):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def track_videos(cfg, hist, now):
    """채널별 업로드 목록에서 최근 7일 영상을 골라 현재 조회수를 기록."""
    vids = load(VOUT, {"videos": {}})
    V = vids["videos"]
    cut = now - datetime.timedelta(hours=TRACK_HOURS)

    targets = {}
    for c in cfg["channels"]:
        cid = hist["ids"].get(c["handle"])
        if not cid:
            continue
        res = api("playlistItems", {"part": "contentDetails", "playlistId": "UU" + cid[2:], "maxResults": 15})
        for it in res.get("items", []):
            vid = it["contentDetails"]["videoId"]
            pub = it["contentDetails"].get("videoPublishedAt")
            if pub and datetime.datetime.fromisoformat(pub.replace("Z", "+00:00")) >= cut:
                targets[vid] = c["handle"]

    ids = list(targets)
    for i in range(0, len(ids), 50):
        res = api("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50])})
        for it in res.get("items", []):
            vid = it["id"]
            pub = datetime.datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z", "+00:00"))
            age = round((now - pub).total_seconds() / 3600, 2)
            st = it["statistics"]
            rec = V.setdefault(vid, {"ch": targets[vid], "p": it["snippet"]["publishedAt"], "pts": []})
            rec["title"] = it["snippet"]["title"]
            rec["sec"] = iso_seconds(it["contentDetails"].get("duration"))
            rec["likes"] = int(st.get("likeCount", 0))
            rec["cm"] = int(st.get("commentCount", 0))
            rec["pts"].append([age, int(st.get("viewCount", 0))])

    vcut = now - datetime.timedelta(days=VKEEP_DAYS)
    vids["videos"] = {
        k: v for k, v in V.items()
        if datetime.datetime.fromisoformat(v["p"].replace("Z", "+00:00")) >= vcut
    }
    vids["updated"] = now.isoformat(timespec="seconds")
    save(VOUT, vids)
    print("영상 기록:", len(ids), "개")


def main():
    cfg = load(CFG, {"channels": []})
    hist = load(OUT, {"ids": {}, "snapshots": []})

    # @핸들 → 채널 ID (한 번만 조회 후 저장)
    for ch in cfg["channels"]:
        k = ch["handle"]
        if ch.get("id"):
            hist["ids"][k] = ch["id"]
        elif k not in hist["ids"]:
            items = api("channels", {"part": "id", "forHandle": k}).get("items") or []
            if items:
                hist["ids"][k] = items[0]["id"]
            else:
                print("채널을 찾지 못함:", k)

    ids = [hist["ids"][c["handle"]] for c in cfg["channels"] if c["handle"] in hist["ids"]]
    stats, titles = {}, {}
    if ids:
        res = api("channels", {"part": "snippet,statistics", "id": ",".join(ids), "maxResults": 50})
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
    save(OUT, hist)
    print("저장:", len(stats), "개 채널")

    # 영상 추적이 실패해도 채널 기록은 이미 저장됨
    try:
        track_videos(cfg, hist, now)
    except Exception as e:
        print("영상 기록 실패:", e)


if __name__ == "__main__":
    main()
