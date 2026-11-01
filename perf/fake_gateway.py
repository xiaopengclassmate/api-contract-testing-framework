"""本地支付网关替身。

压测时不能让被测服务真的去请求外部网关（不确定性太大），
所以用标准库起一个可控的 HTTP 服务，返回固定结构的流水号。
`--gateway-delay-ms` 可以模拟下游慢响应，用于验证超时分支。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    delay_ms = 0

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}

        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)

        body = json.dumps(
            {
                "reference": f"GW-{uuid.uuid4().hex[:12]}",
                "status": "approved",
                "amount": payload.get("amount"),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # 压测时不要刷屏
        return


def serve(port: int = 18080, delay_ms: int = 0) -> ThreadingHTTPServer:
    """启动网关替身，返回 server 对象（调用方负责 shutdown）。"""
    _Handler.delay_ms = delay_ms
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
