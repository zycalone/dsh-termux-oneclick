#!/usr/bin/env python3
"""wxproxy.py —— 极简 HTTP 正向代理，把 User-Agent 改成微信客户端。
用途：某些政务 H5 页面做了 UA 门禁（提示"请在微信客户端打开链接"），
      浏览器走本代理即可正常打开，同时保持页面 origin 不变（不会触发 CORS）。

用法：
  python wxproxy.py 8888
  adb shell settings put global http_proxy 127.0.0.1:8888
  # 用完恢复
  adb shell settings put global http_proxy :0

说明：只改明文 HTTP 的 UA；HTTPS（CONNECT）只做透明隧道，不改包。
"""
import socket
import socketserver
import sys
import urllib.request

UA = ("Mozilla/5.0 (Linux; Android 13; V2546A Build/TP1A.220624.014; wv) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 "
      "Mobile Safari/537.36 MicroMessenger/8.0.49.2600(0x2800313D) "
      "WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64")
HOP = {"connection", "proxy-connection", "keep-alive", "transfer-encoding",
       "te", "trailer", "upgrade", "proxy-authenticate", "proxy-authorization"}


class Handler(socketserver.StreamRequestHandler):
    timeout = 60

    def handle(self):
        try:
            line = self.rfile.readline(65536).decode("latin-1").strip()
            if not line:
                return
            parts = line.split()
            if len(parts) < 3:
                return
            method, url, ver = parts[0], parts[1], parts[2]
            headers = {}
            while True:
                h = self.rfile.readline(65536).decode("latin-1")
                if h in ("\r\n", "\n", ""):
                    break
                if ":" in h:
                    k, v = h.split(":", 1)
                    headers[k.strip()] = v.strip()

            if method.upper() == "CONNECT":
                host, _, port = url.partition(":")
                port = int(port or 443)
                upstream = socket.create_connection((host, port), timeout=20)
                self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.wfile.flush()
                self._tunnel(upstream)
                return

            if not url.lower().startswith("http://"):
                self.wfile.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return

            body = None
            clen = int(headers.get("Content-Length") or 0)
            if clen:
                body = self.rfile.read(clen)

            req = urllib.request.Request(url, data=body, method=method)
            for k, v in headers.items():
                if k.lower() in HOP or k.lower() == "host":
                    continue
                req.add_header(k, v)
            req.add_header("User-Agent", UA)
            req.add_header("X-Requested-With", "com.tencent.mm")
            req.add_header("Referer", "https://servicewechat.com/")

            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    data = r.read()
                    status = r.status
                    hdrs = r.headers
            except urllib.error.HTTPError as e:
                data = e.read()
                status = e.code
                hdrs = e.headers
            except Exception as e:  # noqa: BLE001
                msg = str(e).encode()
                self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: %d\r\n\r\n" % len(msg) + msg)
                return

            out = ["HTTP/1.1 %d %s" % (status, "OK" if status == 200 else "X")]
            for k, v in hdrs.items():
                if k.lower() in HOP:
                    continue
                out.append("%s: %s" % (k, v))
            out.append("Content-Length: %d" % len(data))
            out.append("Connection: close")
            self.wfile.write(("\r\n".join(out) + "\r\n\r\n").encode("latin-1"))
            self.wfile.write(data)
            self.wfile.flush()
        except Exception:  # noqa: BLE001
            pass

    def _tunnel(self, upstream):
        self.connection.settimeout(60)
        upstream.settimeout(60)
        import select
        socks = [self.connection, upstream]
        while True:
            r, _, x = select.select(socks, [], socks, 60)
            if x or not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (upstream if s is self.connection else self.connection).sendall(data)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    print("wxproxy listening on 127.0.0.1:%d" % port, flush=True)
    Server(("127.0.0.1", port), Handler).serve_forever()
