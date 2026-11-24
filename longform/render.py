"""롱폼 렌더러: lines.json(내레이션+화면 지정) → 1920x1080 MP4.

사용법
  python3 longform/render.py longform/<프로젝트폴더>            # 영상
  python3 longform/render.py longform/<프로젝트폴더> --thumb    # 썸네일만
  python3 longform/render.py longform/<프로젝트폴더> --stills   # 장면별 미리보기 PNG

음성(있으면 자동 사용, 우선순위 순)
  1) <폴더>/audio/full.mp3 + <폴더>/audio/timing.json  ([시작초, ...] 줄 순서대로)
  2) <폴더>/audio/line_01.mp3, line_02.mp3 ...           (줄마다 한 파일)
  3) 없으면 글자 수로 길이를 추정하고 무음으로 렌더
"""
import json, math, os, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
FONT_B = ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1)
FONT_R = ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1)
C = {
    "bg": (13, 19, 32), "panel": (24, 33, 54), "line": (48, 60, 88),
    "text": (242, 244, 248), "muted": (138, 150, 173),
    "blue": (57, 135, 229), "red": (229, 72, 77), "yellow": (245, 197, 66),
    "sky": (64, 180, 230), "green": (47, 179, 122),
}
SYL_PER_SEC = 5.4   # 음성 없을 때 길이 추정용 (공백 제외 글자/초)
_fc = {}


def F(size, bold=True):
    k = (size, bold)
    if k not in _fc:
        path, idx = FONT_B if bold else FONT_R
        _fc[k] = ImageFont.truetype(path, size, index=idx)
    return _fc[k]


def col(name):
    return C.get(name, C["yellow"]) if isinstance(name, str) else name


def ease(p):
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def tw(d, s, f):
    b = d.textbbox((0, 0), s, font=f)
    return b[2] - b[0], b[3] - b[1]


def ctext(d, cx, cy, s, f, fill, alpha=1.0, bg=None):
    """가운데 정렬 텍스트(여러 줄 지원). alpha 는 배경과 섞어 흉내."""
    fill = mix(bg or C["bg"], fill, alpha)
    lines = s.split("\n")
    lh = f.size * 1.25
    y0 = cy - lh * len(lines) / 2
    for i, ln in enumerate(lines):
        w, _ = tw(d, ln, f)
        d.text((cx - w / 2, y0 + i * lh), ln, font=f, fill=fill)


def rrect(d, box, r, fill=None, outline=None, width=0):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


# ---------------------------------------------------------------- 화면 종류
CY = 470  # 시각 요소 중심 y (아래는 자막 자리)


def v_date(d, v, p, t):
    a = ease(p)
    c = col(v.get("color", "text"))
    ctext(d, W / 2, CY - 170, v["label"], F(54, False), C["muted"], a)
    ctext(d, W / 2, CY + 10 - 30 * (1 - a), v["value"], F(210), c, a)
    if v.get("sub"):
        ctext(d, W / 2, CY + 190, v["sub"], F(40, False), C["muted"], a)


def v_counter(d, v, p, t):
    a = ease(p)
    k = ease(min(1, t / 1.2))
    n = round(v["from"] + (v["to"] - v["from"]) * k)
    c = col(v.get("color", "yellow"))
    ctext(d, W / 2, CY - 20, f'{v.get("prefix","")}{n}{v.get("suffix","")}', F(260), c, a)
    ctext(d, W / 2, CY + 190, v["label"], F(48, False), C["muted"], a)


def v_stamp(d, v, p, t, img):
    a = ease(p)
    ctext(d, W / 2, CY - 210, v["under"], F(90), C["muted"], a)
    s = ease(min(1, max(0, (t - 0.25) / 0.35)))
    if s > 0:
        c = col(v.get("color", "red"))
        f = F(int(150 + 60 * (1 - s)))
        txt = v["text"]
        layer = Image.new("RGBA", (1100, 420), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        w, h = tw(ld, txt, f)
        bw, bh = w + 120, 260
        bx, by = (1100 - bw) / 2, (420 - bh) / 2
        alpha = int(255 * s)
        ld.rounded_rectangle((bx, by, bx + bw, by + bh), 24, outline=c + (alpha,), width=14)
        ld.text(((1100 - w) / 2, by + (bh - f.size * 1.18) / 2), txt, font=f, fill=c + (alpha,))
        layer = layer.rotate(-8, resample=Image.BICUBIC, expand=False)
        img.paste(layer, (int(W / 2 - 550), int(CY + 20 - 210)), layer)
    if v.get("sub"):
        ctext(d, W / 2, CY + 230, v["sub"], F(44, False), C["text"], s)


def v_options(d, v, p, t):
    items = v["items"]
    n = len(items)
    bw, gap = (380 if n >= 3 else 480), 60
    tot = n * bw + (n - 1) * gap
    x0 = (W - tot) / 2
    hc = col(v.get("color", "yellow"))
    if v.get("head"):
        ctext(d, W / 2, CY - 230, v["head"], F(56), C["text"], ease(p))
    for i, s in enumerate(items):
        delay = i * 0.35 if v.get("seq") else i * 0.12
        a = ease((t - delay) / 0.45)
        if a <= 0:
            continue
        x = x0 + i * (bw + gap)
        y = CY - 140 + 40 * (1 - a)
        hi = (v.get("hi", -1) == i) and (not v.get("seq") or t > 0.35 * i + 0.3)
        fill = mix(C["bg"], C["panel"], a)
        rrect(d, (x, y, x + bw, y + 300), 28, fill=fill,
              outline=mix(C["bg"], hc if hi else C["line"], a), width=8 if hi else 3)
        ctext(d, x + bw / 2, y + 150, s, F(110 if len(s) <= 2 else 80), hc if hi else C["text"], a, fill)


def v_clocks(d, v, p, t):
    items = v["items"]
    hi = v.get("hi", -1)
    if v.get("head"):
        ctext(d, W / 2, CY - 250, v["head"], F(60), C["yellow"], ease(p))
    gap = 540
    for i, (val, lab) in enumerate(items):
        a = ease((t - i * 0.18) / 0.5)
        if a <= 0:
            continue
        cx = W / 2 + (i - 1) * gap * (1 - (0.3 * ease((t - 0.6) / 0.8) if hi == 3 else 0))
        cy = CY - 10
        r = 170
        oc = C["yellow"] if (hi == i or hi == 3) else C["blue"]
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=mix(C["bg"], C["panel"], a),
                  outline=mix(C["bg"], oc, a), width=10)
        ang = -math.pi / 2 + t * 1.6 + i * 2.1
        d.line((cx, cy, cx + math.cos(ang) * r * 0.78, cy + math.sin(ang) * r * 0.78),
               fill=mix(C["bg"], oc, a * 0.5), width=6)
        ctext(d, cx, cy, val, F(84), C["text"], a, C["panel"])
        ctext(d, cx, cy + r + 60, lab, F(46, False), C["muted"], a)


def v_section(d, v, p, t):
    a = ease(p)
    ctext(d, W / 2, CY - 150, v["num"], F(60), C["blue"], a)
    ctext(d, W / 2, CY + 10 - 40 * (1 - a), v["title"], F(170), C["text"], a)
    bw = 520 * ease((t - 0.2) / 0.6)
    d.rectangle((W / 2 - bw / 2, CY + 135, W / 2 + bw / 2, CY + 143), fill=C["blue"])
    ctext(d, W / 2, CY + 215, v["sub"], F(46, False), C["muted"], ease((t - 0.3) / 0.5))


def v_timeline(d, v, p, t):
    steps = v["steps"]
    n = len(steps)
    hi = v.get("hi", -1)
    if v.get("head"):
        ctext(d, W / 2, CY - 260, v["head"], F(56), C["text"], ease(p))
    x0, x1 = 300, W - 300
    y = CY + 10
    lw = (x1 - x0) * ease(t / 0.7)
    d.rectangle((x0, y - 5, x0 + lw, y + 5), fill=C["line"])
    for i, (top, bot) in enumerate(steps):
        x = x0 + (x1 - x0) * i / (n - 1)
        a = ease((t - 0.15 - i * 0.15) / 0.4)
        if a <= 0:
            continue
        is_hi = i == hi
        c = C["yellow"] if is_hi else C["blue"]
        r = 30 if is_hi else 22
        d.ellipse((x - r, y - r, x + r, y + r), fill=mix(C["bg"], c, a))
        ctext(d, x, y - 110, top, F(56), C["text"] if is_hi else C["muted"], a)
        ctext(d, x, y + 110, bot, F(70 if is_hi else 58), c if is_hi else C["text"], a)
    if v.get("note") and hi >= 0:
        x = x0 + (x1 - x0) * hi / (n - 1)
        ctext(d, x, y + 215, v["note"], F(42, False), C["yellow"], ease((t - 0.7) / 0.4))


def v_quote(d, v, p, t):
    a = ease(p)
    c = col(v.get("color", "blue"))
    bw, bh = 1300, 500
    x, y = (W - bw) / 2, CY - bh / 2 - 10 + 40 * (1 - a)
    rrect(d, (x, y, x + bw, y + bh), 32, fill=mix(C["bg"], C["panel"], a))
    d.rectangle((x, y + 40, x + 16, y + bh - 40), fill=mix(C["bg"], c, a))
    rrect(d, (x + 70, y - 34, x + 70 + tw(d, v["who"], F(46))[0] + 60, y + 40), 20, fill=mix(C["bg"], c, a))
    d.text((x + 100, y - 30), v["who"], font=F(46), fill=mix(C["bg"], C["text"], a))
    ctext(d, W / 2 + 10, y + bh / 2 + 10, v["text"], F(92), C["text"], a, C["panel"])


def v_bignum(d, v, p, t):
    a = ease(p)
    k = ease(min(1, t / 1.0))
    n = round(v["value"] * k)
    c = col(v.get("color", "yellow"))
    f1, f2 = F(280), F(110)
    s1, s2 = f"{n:,}", v["unit"]
    w1, w2 = tw(d, s1, f1)[0], tw(d, s2, f2)[0]
    x = W / 2 - (w1 + w2 + 20) / 2
    d.text((x, CY - 230), s1, font=f1, fill=mix(C["bg"], c, a))
    d.text((x + w1 + 20, CY - 35), s2, font=f2, fill=mix(C["bg"], c, a))
    ctext(d, W / 2, CY + 200, v["label"], F(50, False), C["muted"], ease((t - 0.3) / 0.5))


def v_big(d, v, p, t):
    a = ease(p)
    s = v["text"]
    size = 200 if len(s) <= 4 else 150
    ctext(d, W / 2, CY - 10 + 30 * (1 - a), s, F(size), col(v.get("color", "text")), a)


def v_flow(d, v, p, t):
    items = v["items"]
    n = len(items)
    hi = v.get("hi", -1)
    hc = col(v.get("color", "yellow"))
    bw = 470 if n >= 3 else 600
    gap = 130
    tot = n * bw + (n - 1) * gap
    x0 = (W - tot) / 2
    y = CY - 110
    for i, s in enumerate(items):
        a = ease((t - i * 0.4) / 0.45)
        if a <= 0:
            continue
        x = x0 + i * (bw + gap)
        is_hi = i == hi
        rrect(d, (x, y, x + bw, y + 220), 26, fill=mix(C["bg"], C["panel"], a),
              outline=mix(C["bg"], hc if is_hi else C["line"], a), width=8 if is_hi else 3)
        ctext(d, x + bw / 2, y + 110, s, F(64), hc if is_hi else C["text"], a, C["panel"])
        if i < n - 1:
            aa = ease((t - i * 0.4 - 0.3) / 0.3)
            ax = x + bw + 25
            d.polygon([(ax, y + 80), (ax + 70 * aa, y + 110), (ax, y + 140)], fill=C["muted"])


def v_bars(d, v, p, t):
    items = v["items"]
    mx = v["max"]
    x0, x1 = 520, W - 260
    n = len(items)
    rowh = 150 if n <= 2 else 115
    y0 = CY - rowh * n / 2
    for i, (lab, val, cn) in enumerate(items):
        a = ease((t - i * 0.2) / 0.5)
        if a <= 0:
            continue
        k = ease((t - i * 0.2) / 0.9)
        y = y0 + i * rowh
        c = col(cn)
        d.text((x0 - 40 - tw(d, lab, F(56))[0], y + 8), lab, font=F(56), fill=mix(C["bg"], C["text"], a))
        bw = (x1 - x0) * val / mx * k
        rrect(d, (x0, y + 10, x0 + max(bw, 12), y + rowh - 30), 14, fill=c)
        s = f"{round(val * k)}{v.get('unit','')}"
        d.text((x0 + bw + 24, y + 4), s, font=F(64), fill=mix(C["bg"], c, a))


def v_window(d, v, p, t):
    marks, labels = v["marks"], v["labels"]
    x0, x1 = 300, W - 300
    y = CY + 20
    sx = lambda h: x0 + (x1 - x0) * h / marks[-1]
    a = ease(p)
    d.rectangle((x0, y - 6, x1, y + 6), fill=mix(C["bg"], C["line"], a))
    z = ease((t - 0.5) / 0.6)
    if z > 0:
        xa, xb = sx(marks[1]), sx(marks[1]) + (sx(marks[2]) - sx(marks[1])) * z
        rrect(d, (xa, y - 70, xb, y + 70), 18, fill=mix(C["bg"], C["yellow"], 0.35))
        ctext(d, (sx(marks[1]) + sx(marks[2])) / 2, y - 150, v["zone"], F(64), C["yellow"], z)
    for h, lab in zip(marks, labels):
        x = sx(h)
        d.ellipse((x - 20, y - 20, x + 20, y + 20), fill=mix(C["bg"], C["blue"], a))
        ctext(d, x, y + 120, lab, F(52), C["text"], a)


# 12/1 ~ 6/30 축 위의 날짜 (일 단위)
def _dayx(day, x0=180, x1=W - 180, span=212):
    return x0 + (x1 - x0) * day / span


D_DEC7, D_JUN5 = 6, 186     # 2026-12-01 기준 일수
D_SOCHU = 14                # 예시 소추일 12/15


def v_range(d, v, p, t):
    mode = v["mode"]
    y = CY + 40
    a = ease(p)
    d.rectangle((_dayx(0), y - 5, _dayx(212), y + 5), fill=mix(C["bg"], C["line"], a))
    for day, lab in [(0, "12월"), (31, "1월"), (62, "2월"), (90, "3월"), (121, "4월"), (151, "5월"), (182, "6월")]:
        x = _dayx(day)
        d.rectangle((x - 2, y - 18, x + 2, y + 18), fill=C["line"])
        d.text((x + 8, y + 22), lab, font=F(34, False), fill=mix(C["bg"], C["muted"], a))
    xj = _dayx(D_JUN5)
    d.rectangle((xj - 4, y - 260, xj + 4, y + 90), fill=C["red"])
    ctext(d, xj, y - 300, "정년 6.5", F(52), C["red"], a)
    if mode == "back":
        k = ease((t - 0.3) / 1.4)
        xs = xj - (xj - _dayx(D_DEC7)) * k
        rrect(d, (xs, y - 120, xj, y - 50), 14, fill=mix(C["bg"], C["yellow"], 0.45))
        ctext(d, (xs + xj) / 2, y - 85, "180일", F(48), C["text"], k)
        if k > 0.95:
            x7 = _dayx(D_DEC7)
            d.rectangle((x7 - 4, y - 260, x7 + 4, y + 90), fill=C["yellow"])
            ctext(d, x7 + 40, y - 300, "12.7", F(60), C["yellow"], 1)
    else:
        x7 = _dayx(D_DEC7)
        d.rectangle((x7 - 3, y - 200, x7 + 3, y + 60), fill=mix(C["bg"], C["yellow"], 0.7))
        ctext(d, x7 + 20, y - 230, "12.7", F(44), C["yellow"], 0.8)
        xs = _dayx(D_SOCHU)
        k = ease((t - 0.3) / 1.4)
        xe = xs + (_dayx(D_SOCHU + 180) - xs) * k
        mid = min(xe, xj)
        rrect(d, (xs, y - 120, mid, y - 50), 14, fill=mix(C["bg"], C["blue"], 0.6))
        if xe > xj:
            rrect(d, (xj, y - 120, xe, y - 50), 14, fill=C["red"])
        ctext(d, (xs + mid) / 2, y - 85, "헌재 180일", F(44), C["text"], k)
        ctext(d, xs + 10, y + 120, "소추(예: 12.15)", F(40), C["blue"], a)
        if mode == "retire" and k > 0.9:
            rrect(d, (xj - 230, y + 150, xj + 230, y + 250), 20, fill=C["red"])
            ctext(d, xj, y + 200, "결정 전 퇴직", F(54), C["text"], 1, C["red"])


def v_meter(d, v, p, t):
    x0, x1 = 260, W - 260
    y = CY - 40
    a = ease(p)
    ctext(d, W / 2, y - 200, "남은 임기  11.24 → 6.5", F(56), C["text"], a)
    rrect(d, (x0, y - 60, x1, y + 60), 24, fill=mix(C["bg"], C["panel"], a))
    xs = x0 + (x1 - x0) * 21 / 193       # 12/15 소추 가정
    k = ease((t - 0.4) / 1.2)
    rrect(d, (x0, y - 60, xs, y + 60), 24, fill=C["blue"])
    if k > 0:
        rrect(d, (xs, y - 60, xs + (x1 - xs) * k, y + 60), 24, fill=C["red"])
        ctext(d, (xs + x1) / 2, y, "직무 정지", F(64), C["text"], k, C["red"])
    ctext(d, x0 + 90, y + 120, "소추", F(42), C["blue"], a)
    ctext(d, W / 2, y + 230, "* 12월 중순 소추 가정", F(36, False), C["muted"], a)


VIS = {
    "date": v_date, "counter": v_counter, "stamp": v_stamp, "options": v_options,
    "clocks": v_clocks, "section": v_section, "timeline": v_timeline, "quote": v_quote,
    "bignum": v_bignum, "big": v_big, "flow": v_flow, "bars": v_bars,
    "window": v_window, "range": v_range, "meter": v_meter,
}


# ---------------------------------------------------------------- 자막
def chunks(text, maxlen=28):
    """문장부호로 나누고, 긴 문장은 비슷한 길이로 균등 분할(공백 기준)."""
    parts = [s.strip() for s in re.split(r"(?<=[,.?!])\s+", text) if s.strip()]
    out = []
    for s in parts:
        n = math.ceil(len(s) / maxlen)
        if n <= 1:
            out.append(s)
            continue
        words, cur, target = s.split(" "), "", len(s) / n
        for w_ in words:
            if cur and len(cur) + 1 + len(w_) > target * 1.15 and len(out) < 10 ** 6:
                out.append(cur)
                cur = w_
            else:
                cur = f"{cur} {w_}".strip()
        if cur:
            out.append(cur)
    return out


def sub_layer(text):
    f = F(58)
    img = Image.new("RGBA", (W, 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w, h = tw(d, text, f)
    pad = 34
    d.rounded_rectangle(((W - w) / 2 - pad, 20, (W + w) / 2 + pad, 140), 18, fill=(0, 0, 0, 190))
    d.text(((W - w) / 2, 34), text, font=f, fill=(255, 255, 255))
    return img


# ---------------------------------------------------------------- 프레임
def base_frame(proj, line, t, li, n):
    img = Image.new("RGB", (W, H), C["bg"])
    d = ImageDraw.Draw(img)
    # 상단 고정 정보
    d.text((70, 48), "이슈러쉬", font=F(40), fill=C["blue"])
    d.text((70 + tw(d, "이슈러쉬", F(40))[0] + 24, 50), proj["tag"], font=F(38, False), fill=C["muted"])
    sec = line["sec"]
    sw = tw(d, sec, F(38))[0]
    rrect(d, (W - 70 - sw - 50, 40, W - 70, 104), 32, fill=C["panel"])
    d.text((W - 70 - sw - 25, 46), sec, font=F(38), fill=C["text"])
    v = line["v"]
    fn = VIS[v["type"]]
    p = min(1.0, t / 0.55)
    if v["type"] == "stamp":
        fn(d, v, p, t, img)
    else:
        fn(d, v, p, t)
    return img


def durations(proj_dir, lines):
    ad = os.path.join(proj_dir, "audio")
    tj = os.path.join(ad, "timing.json")
    if os.path.exists(tj) and os.path.exists(os.path.join(ad, "full.mp3")):
        starts = json.load(open(tj))
        total = probe(os.path.join(ad, "full.mp3"))
        ends = starts[1:] + [total]
        return [e - s for s, e in zip(starts, ends)], ("full", os.path.join(ad, "full.mp3"))
    files = [os.path.join(ad, f"line_{i+1:02d}.mp3") for i in range(len(lines))]
    if all(os.path.exists(f) for f in files):
        return [probe(f) + 0.3 for f in files], ("lines", files)
    est = [len(re.sub(r"\s", "", l["text"])) / SYL_PER_SEC + 0.45 for l in lines]
    return est, None


def probe(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", f], capture_output=True, text=True)
    return float(r.stdout.strip())


def render(proj_dir, stills=False):
    proj = json.load(open(os.path.join(proj_dir, "lines.json")))
    lines = proj["lines"]
    durs, audio = durations(proj_dir, lines)
    total = sum(durs)
    print(f"{len(lines)}줄, 총 {total/60:.1f}분, 음성: {audio[0] if audio else '없음(추정 길이)'}")
    if stills:
        os.makedirs(os.path.join(proj_dir, "stills"), exist_ok=True)
        for i, l in enumerate(lines):
            img = base_frame(proj, l, 2.5, i, len(lines))
            ch = chunks(l["text"])
            img.paste(sub_layer(ch[0]), (0, H - 230), sub_layer(ch[0]))
            img.save(os.path.join(proj_dir, "stills", f"{i+1:02d}.png"))
        return
    out = os.path.join(proj_dir, "out.mp4")
    silent = os.path.join(proj_dir, "_video.mp4")
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", silent],
                           stdin=subprocess.PIPE)
    elapsed = 0.0
    for i, (l, dur) in enumerate(zip(lines, durs)):
        ch = chunks(l["text"])
        wts = [len(c) for c in ch]
        bounds, acc = [], 0
        for w_ in wts:
            acc += w_
            bounds.append(dur * acc / sum(wts))
        subs = [sub_layer(c) for c in ch]
        nf = int(round(dur * FPS))
        cache = None
        for fi in range(nf):
            t = fi / FPS
            anim = t < 2.2 or l["v"]["type"] == "clocks"
            if anim or cache is None:
                frame = base_frame(proj, l, t, i, len(lines))
                if not anim:
                    cache = frame
            else:
                frame = cache.copy()
            si = next((k for k, b in enumerate(bounds) if t < b), len(subs) - 1)
            frame.paste(subs[si], (0, H - 230), subs[si])
            pd = ImageDraw.Draw(frame)
            pd.rectangle((0, H - 8, W * (elapsed + t) / total, H), fill=C["blue"])
            enc.stdin.write(frame.tobytes())
        elapsed += dur
        print(f"  {i+1}/{len(lines)}", end="\r", flush=True)
    enc.stdin.close()
    enc.wait()
    # 오디오 합치기
    if audio and audio[0] == "full":
        a_args = ["-i", audio[1]]
    elif audio:
        lst = os.path.join(proj_dir, "_alist.txt")
        with open(lst, "w") as fh:
            for f_, dur in zip(audio[1], durs):
                fh.write(f"file '{os.path.abspath(f_)}'\n")
        a_args = ["-f", "concat", "-safe", "0", "-i", lst]
    else:
        a_args = ["-f", "lavfi", "-t", str(total), "-i", "anullsrc=r=44100:cl=stereo"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, *a_args,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out], check=True)
    os.remove(silent)
    print(f"\n완료: {out}")


def thumb(proj_dir):
    img = Image.new("RGB", (1280, 720), C["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1280, 720), fill=C["bg"])
    d.rectangle((0, 0, 22, 720), fill=C["red"])
    d.text((70, 60), "조희대 탄핵", font=F(110), fill=C["text"])
    d.text((70, 200), "가결 = 끝?", font=F(150), fill=C["yellow"])
    y = 450
    for i, (val, lab) in enumerate([("12.2", "예산"), ("180일", "헌재"), ("6.5", "정년")]):
        x = 70 + i * 395
        rrect(d, (x, y, x + 360, y + 200), 24, fill=C["panel"], outline=C["red"] if i == 2 else C["line"], width=6)
        ctext(d, x + 180, y + 80, val, F(96), C["red"] if i == 2 else C["text"], 1, C["panel"])
        ctext(d, x + 180, y + 160, lab, F(40, False), C["muted"], 1, C["panel"])
    img.save(os.path.join(proj_dir, "thumbnail.png"))
    print("썸네일 저장")


if __name__ == "__main__":
    pd_ = sys.argv[1]
    if "--thumb" in sys.argv:
        thumb(pd_)
    elif "--stills" in sys.argv:
        render(pd_, stills=True)
    else:
        render(pd_)
