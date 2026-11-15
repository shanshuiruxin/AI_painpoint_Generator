import http.server
import json
import socketserver
from typing import Iterator

import requests


PORT = 8000
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def iter_deepseek_content(response: requests.Response) -> Iterator[str]:
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue

        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line.startswith("data:"):
            continue

        data = line[5:].strip()
        if data == "[DONE]":
            break

        event = json.loads(data)
        if not isinstance(event, dict):
            raise ValueError("DeepSeek 返回了无效的流数据。")
        if event.get("error"):
            raise RuntimeError("DeepSeek 流式请求返回错误。")

        choices = event.get("choices")
        if not isinstance(choices, list) or not choices:
            continue

        delta = choices[0].get("delta", {})
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield content


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def send_json_error(self, status: int, message: str):
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_sse_event(self, event_name: str, data):
        serialized = json.dumps(data, ensure_ascii=False)
        event = f"event: {event_name}\ndata: {serialized}\n\n"
        self.wfile.write(event.encode("utf-8"))
        self.wfile.flush()

    def do_POST(self):
        if self.path != "/api/generate":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 1024 * 1024:
                self.send_json_error(400, "请求内容为空或过大。")
                return

            data = json.loads(self.rfile.read(content_length))
        except (ValueError, json.JSONDecodeError):
            self.send_json_error(400, "请求必须是有效的 JSON。")
            return

        api_key = data.get("apiKey") if isinstance(data, dict) else None
        audience = data.get("audience") if isinstance(data, dict) else None

        if not isinstance(api_key, str) or not api_key.strip():
            self.send_json_error(400, "请提供 DeepSeek API Key。")
            return
        if not isinstance(audience, str) or not audience.strip():
            self.send_json_error(400, "请提供要分析的人群。")
            return

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一位产品研究助手。请根据用户指定的人群，分析其常见但具体的痛点，"
                        "并提出一个轻量、可执行的解决方案。只返回 JSON 对象，格式为 "
                        '{"pains":["痛点1","痛点2","痛点3"],"solution":"解决方案"}。'
                        "pains 必须恰好包含 3 条简洁、具体的中文描述，"
                        "solution 必须是一段可执行的中文建议。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"请分析这类人群：{audience.strip()}",
                },
            ],
            "response_format": {"type": "json_object"},
            "stream": True,
        }

        try:
            upstream_response = requests.post(
                DEEPSEEK_URL,
                headers={
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=payload,
                stream=True,
                timeout=(10, 120),
            )
            upstream_response.raise_for_status()
        except requests.RequestException as error:
            self.send_json_error(502, f"DeepSeek API 请求失败：{error}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            with upstream_response:
                for content in iter_deepseek_content(upstream_response):
                    self.send_sse_event("message", content)
            self.send_sse_event("done", {"done": True})
        except (
            requests.RequestException,
            json.JSONDecodeError,
            RuntimeError,
            ValueError,
        ) as error:
            self.send_sse_event("error", {"error": f"读取 DeepSeek 流失败：{error}"})


print(f"服务器已启动！请打开: http://localhost:{PORT}")
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()