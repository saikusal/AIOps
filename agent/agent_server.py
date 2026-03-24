import json
import os
import shlex
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


HOST = os.getenv("AGENT_BIND", "0.0.0.0")
PORT = int(os.getenv("AGENT_PORT", "9999"))
AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN", "aiops-demo-agent-7f3c29d1b84e4a6f")
REQUEST_TIMEOUT = int(os.getenv("AGENT_REQUEST_TIMEOUT", "60"))
ALLOWED_COMMANDS_FILE = Path(
    os.getenv("AGENT_ALLOWED_COMMANDS_FILE", Path(__file__).with_name("allowed_commands.json"))
)


def load_allowed_prefixes():
    if not ALLOWED_COMMANDS_FILE.exists():
        return []
    data = json.loads(ALLOWED_COMMANDS_FILE.read_text())
    return [tuple(item) for item in data.get("allowed_prefixes", []) if item]


ALLOWED_PREFIXES = load_allowed_prefixes()


def is_command_allowed(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False
    for prefix in ALLOWED_PREFIXES:
        if tuple(tokens[: len(prefix)]) == prefix:
            return True
    return False


class AgentHandler(BaseHTTPRequestHandler):
    server_version = "AIOpsAgent/0.1"

    def _json_response(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/execute":
            self._json_response(404, {"error": "not_found"})
            return

        if not AUTH_TOKEN:
            self._json_response(500, {"error": "AGENT_AUTH_TOKEN is not configured"})
            return

        auth_header = self.headers.get("Authorization", "")
        if auth_header != f"Bearer {AUTH_TOKEN}":
            self._json_response(401, {"error": "unauthorized"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length) or b"{}")
        except Exception as exc:
            self._json_response(400, {"error": "invalid_json", "detail": str(exc)})
            return

        command = (payload.get("command") or "").strip()
        if not command:
            self._json_response(400, {"error": "command_required"})
            return
        if not is_command_allowed(command):
            self._json_response(403, {"error": "command_not_allowed", "command": command})
            return

        try:
            tokens = shlex.split(command)
            proc = subprocess.run(
                tokens,
                capture_output=True,
                text=True,
                timeout=REQUEST_TIMEOUT,
                check=False,
            )
            self._json_response(
                200,
                {
                    "command": command,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "output": (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else ""),
                },
            )
        except subprocess.TimeoutExpired:
            self._json_response(504, {"error": "command_timeout", "command": command})
        except Exception as exc:
            self._json_response(500, {"error": "command_failed", "detail": str(exc), "command": command})

    def log_message(self, format, *args):
        return


def main():
    server = HTTPServer((HOST, PORT), AgentHandler)
    print(f"AIOps agent listening on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
