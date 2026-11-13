// 스튜디오 '수익 창출' 화면에서 조건 진행 숫자를 읽어 받이(collect_server.py)로 보낸다. 읽기만 한다.
// 쓰는 법: 맨 아래 NAME 을 "<채널 short>_monet" 로 바꿔 /monetization/overview 화면에서 실행.
((NAME) => {
  const out = [];
  const walk = n => {
    if (!n) return;
    if (n.nodeType === 3) { const t = n.textContent.trim(); if (t) out.push(t); return; }
    if (n.nodeType !== 1 && n.nodeType !== 11) return;
    if (n.tagName === "SCRIPT" || n.tagName === "STYLE") return;
    if (n.shadowRoot) walk(n.shadowRoot);
    for (const c of n.childNodes) walk(c);
  };
  walk(document.querySelector("main") || document.body);
  const s = out.join(" | "), g = r => (s.match(r) || [])[1] || null;
  const o = {
    name: NAME, read_at: new Date().toISOString(),
    as_of: g(/(\d{4}\. \d+\. \d+\.) 기준/),
    subs: g(/구독자 ([\d,.만천]+)명 \| 1,000/),
    watch_h: g(/유효 시청 시간 ([\d,.만천]+)시간 \| 최근 365일 \| 4,000/),
    shorts: g(/유효 Shorts 조회수 ([\d,.만천억]+)회 \| 지난 90일 \| 1000만/),
    note: g(/(거주 국가[^|]{0,40})/),
  };
  new Image().src = "http://127.0.0.1:8765/put?name=" + NAME + "&i=0&n=1&d=" + encodeURIComponent(JSON.stringify(o));
  return o;
})("NAME")
