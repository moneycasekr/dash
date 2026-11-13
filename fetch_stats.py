"""유튜브 채널 통계 수집 — GitHub Actions가 1시간마다 실행.
- data/history.json : 채널 전체 숫자 (조회·구독·영상 수). 최근 35일은 1시간 간격, 그 전은 하루 1개.
- data/videos.json  : 채널의 모든 공개 영상. 지금 조회수·좋아요·댓글 + 업로드 후 시간대별 조회수
                      (7일까지 1시간 간격, 그 뒤는 하루 1개).

channels.json 의 handle 은 데이터 열쇠로 쓰인다(id 가 있으면 그 id 로 조회하므로 실제 @핸들과 달라도 됨).
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
HOURLY_DAYS = 35        # 채널 기록: 이 기간은 1시간 간격 그대로
KEEP_DAYS = 800         # 채널 기록: 그 전은 하루 1개로 줄여 이만큼 보관
TRACK_HOURS = 168       # 영상: 업로드 후 7일까지 매시간 기록
SLOW_GAP_HOURS = 23     # 영상: 7일 뒤에는 이 간격(약 하루)으로 기록
MAX_PAGES = 10          # 채널당 업로드 목록 최대 500개
KST = datetime.timezone(datetime.timedelta(hours=9))
KEY = os.environ.get("YT_API_KEY", "")


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


def parse(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def iso_seconds(dur):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def thin_snapshots(snaps, now):
    """최근 HOURLY_DAYS 일은 그대로, 그 전은 한국 날짜마다 마지막 기록 1개만 남긴다."""
    hourly_cut = now - datetime.timedelta(days=HOURLY_DAYS)
    keep_cut = now - datetime.timedelta(days=KEEP_DAYS)
    old_by_day, recent = {}, []
    for s in snaps:
        t = parse(s["t"])
        if t < keep_cut:
            continue
        if t >= hourly_cut:
            recent.append(s)
        else:
            old_by_day[t.astimezone(KST).date()] = s   # 같은 날이면 뒤의 것이 덮어씀
    return [old_by_day[d] for d in sorted(old_by_day)] + recent


def upload_ids(cid):
    """채널 업로드 목록 전체(공개 영상)의 영상 ID."""
    ids, token = [], None
    for _ in range(MAX_PAGES):
        params = {"part": "contentDetails", "playlistId": "UU" + cid[2:], "maxResults": 50}
        if token:
            params["pageToken"] = token
        res = api("playlistItems", params)
        ids += [it["contentDetails"]["videoId"] for it in res.get("items", [])]
        token = res.get("nextPageToken")
        if not token:
            break
    return ids


def track_videos(cfg, hist, now):
    vids = load(VOUT, {"videos": {}})
    V = vids["videos"]
    stamp = now.isoformat(timespec="seconds")

    owner = {}
    for c in cfg["channels"]:
        cid = hist["ids"].get(c["handle"])
        if not cid:
            continue
        try:
            for vid in upload_ids(cid):
                owner[vid] = c["handle"]
        except Exception as e:
            print("업로드 목록 실패:", c["handle"], e)

    ids = list(owner)
    for i in range(0, len(ids), 50):
        res = api("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50])})
        for it in res.get("items", []):
            vid = it["id"]
            pub = parse(it["snippet"]["publishedAt"])
            age = round((now - pub).total_seconds() / 3600, 2)
            st = it["statistics"]
            views = int(st.get("viewCount", 0))
            rec = V.setdefault(vid, {"ch": owner[vid], "p": it["snippet"]["publishedAt"], "pts": []})
            rec["ch"] = owner[vid]
            rec["title"] = it["snippet"]["title"]
            rec["sec"] = iso_seconds(it["contentDetails"].get("duration"))
            rec["likes"] = int(st.get("likeCount", 0))
            rec["cm"] = int(st.get("commentCount", 0))
            rec["v"] = views
            rec["seen"] = stamp          # 이번 수집에서 보인 영상 (지워졌거나 비공개가 되면 옛 시각으로 남음)
            pts = rec["pts"]
            if age <= TRACK_HOURS or not pts or age - pts[-1][0] >= SLOW_GAP_HOURS:
                pts.append([age, views])

    vids["updated"] = stamp
    save(VOUT, vids)
    print("영상 기록:", len(ids), "개")


def main():
    cfg = load(CFG, {"channels": []})
    hist = load(OUT, {"ids": {}, "snapshots": []})

    # 채널 ID: channels.json 에 id 가 있으면 그대로, 없으면 @핸들로 한 번만 조회
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
    hist["snapshots"] = thin_snapshots(hist["snapshots"], now)
    hist["channels"] = [
        {"handle": c["handle"], "id": hist["ids"].get(c["handle"]), "short": c.get("short"),
         "name": c.get("name") or titles.get(c["handle"], c["handle"]), "color": c["color"]}
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
