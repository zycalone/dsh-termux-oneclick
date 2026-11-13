#!/usr/bin/env python3
"""mock_gw.py —— 本地假网关：不用真端点、不用手机，也能验证 llm.py 的回退逻辑

用法（PC 或手机都行，只用标准库）：
  python mock_gw.py 18080 &
  python test_fallback_offline.py

路由：
  /v1/ok/chat/completions     正常返回（会回显收到的图片 mime，验证 vision 消息拼对了没）
  /v1/fail/chat/completions   永远 500
  /v1/empty/chat/completions  200 但 content 为空（模拟"接口活着但不干活"）
  /v1/404/chat/completions    404（验证 4xx 立即换、不重试）
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        model = body.get("model", "?")
        m = re.search(r"/v1/(\w+)/", self.path)
        mode = m.group(1) if m else "ok"

        if mode == "fail":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        if mode == "404":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"no such model"}')
            return
        if mode == "empty":
            self._ok("")
            return

        mime = "text-only"
        for msg in body.get("messages") or []:
            c = msg.get("content")
            if isinstance(c, list):
                for part in c:
                    if part.get("type") == "image_url":
                        mime = part["image_url"]["url"].split(";")[0].replace("data:", "")
        self._ok("MOCK_OK model=%s mime=%s" % (model, mime))

    def _ok(self, text):
        data = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    print("mock gateway on 127.0.0.1:%d" % port, flush=True)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
