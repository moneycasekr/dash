"""스튜디오 화면에서 읽은 표를 이 컴퓨터 파일로 받아 적는 작은 받이 (127.0.0.1 전용).

    python studio/collect_server.py        # 켜 두고, 수집이 끝나면 끈다

스튜디오 화면의 읽기 식(send.js)이 표를 여러 조각으로 나눠
http://127.0.0.1:8765/put?name=<파일 이름>&i=<조각 번호>&n=<조각 수>&d=<내용> 으로 보내면
조각이 다 모였을 때 studio/raw/<파일 이름>.json 으로 저장한다. 바깥 인터넷으로는 아무것도 보내지 않는다.
"""
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")
parts = {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query, keep_blank_values=True)
        msg = "ok"
        if u.path == "/put":
            name = re.sub(r"[^\w-]", "", q.get("name", [""])[0])[:60]
            try:
                i, n = int(q["i"][0]), int(q["n"][0])
            except Exception:
                i, n = -1, 0
            if name and 0 <= i < n <= 400:
                box = parts.setdefault((name, n), {})
                box[i] = q.get("d", [""])[0]
                if len(box) == n:
                    os.makedirs(RAW, exist_ok=True)
                    with open(os.path.join(RAW, name + ".json"), "w", encoding="utf-8") as f:
                        f.write("".join(box[k] for k in range(n)))
                    del parts[(name, n)]
                    print("저장:", name, flush=True)
            else:
                msg = "bad"
        self.send_response(200)
        self.send_header("Content-Type", "image/gif" if u.path == "/put" else "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(GIF if u.path == "/put" else msg.encode())


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print("받이 켜짐: 127.0.0.1:%d → %s" % (port, RAW), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
