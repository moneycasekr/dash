// 스튜디오 '고급 모드' 표를 읽어 이 컴퓨터의 받이(collect_server.py)로 보낸다. 읽기만 하고 아무것도 누르지 않는다.
// 쓰는 법: 맨 아래 NAME 을 "<채널 열쇠>_<videos|daily|traffic>" 로 바꿔 스튜디오 표 화면에서 실행.
// 돌려주는 값: {name, rows, range, more(다음 쪽 있음), err(화면에 오류 글자), sent(보낸 조각 수)}
((NAME) => {
  const all = [];
  const walk = n => { if (!n) return; if (n.nodeType === 1) { all.push(n); if (n.shadowRoot) walk(n.shadowRoot); } for (const c of (n.children || [])) walk(c); };
  walk(document.body);
  const by = t => all.filter(e => e.tagName.toLowerCase() === t);
  const txt = e => (e ? e.innerText.trim().replace(/\s+/g, " ") : "");
  const heads = by("yta-explore-table-header-cell").map(e => e.innerText.trim().split("\n")[0]);
  const rows = [];
  for (const r of by("yta-explore-table-row")) {
    const vals = [...r.querySelectorAll(".debug-metric-value")].map(txt);
    const a = [...r.querySelectorAll("a[href]")].map(x => x.getAttribute("href")).find(h => /video\//.test(h)) || "";
    const img = (r.querySelector("img") || {}).src || "";
    const id = (a.match(/video\/([\w-]{11})/) || img.match(/vi\/([\w-]{11})/) || [])[1];
    const name = txt(r.querySelector(".debug-dimension-value")) || txt(r.querySelector(".dimension-column"));
    rows.push([id || name, ...vals]);
  }
  const range = (all.filter(e => e.children.length === 0 && /\d{4}\. \d+\. \d+\. ~/.test(e.textContent || "")).map(e => e.textContent.trim())[0]) || "";
  const next = all.find(e => e.id === "navigate-after");
  const more = !!(next && !next.hasAttribute("disabled") && next.getAttribute("aria-disabled") !== "true");
  const err = all.some(e => e.children.length === 0 && /오류가 발생했습니다/.test(e.textContent || "") && e.offsetParent);
  const body = JSON.stringify({ name: NAME, read_at: new Date().toISOString(), range, heads, rows, more, err });
  const SZ = 1200, n = Math.ceil(body.length / SZ);
  for (let i = 0; i < n; i++) {
    new Image().src = "http://127.0.0.1:8765/put?name=" + NAME + "&i=" + i + "&n=" + n + "&d=" + encodeURIComponent(body.slice(i * SZ, (i + 1) * SZ));
  }
  return { name: NAME, rows: rows.length, range, more, err, sent: n, first: rows[0] && rows[0].slice(0, 4) };
})("NAME")
