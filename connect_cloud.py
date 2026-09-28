from __future__ import annotations

import hmac
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from hindsight_client import Hindsight


ROOT = Path(__file__).resolve().parent
CLOUD_ORIGIN = "https://ui.hindsight.vectorize.io"
API_URL = "https://api.hindsight.vectorize.io"
BANK_ID = "shiftline-acme-logistics"
APP_PORT = 8000
APP_URL = f"http://127.0.0.1:{APP_PORT}"


def make_handler(server_nonce: str):
    class CloudCredentialHandler(BaseHTTPRequestHandler):
        server_version = "ShiftlineCloudConnector/1.0"

        def log_message(self, format: str, *args: object) -> None:
            status = str(args[1]) if len(args) > 1 else "unknown"
            print(f"Cloud credential handoff request completed: HTTP {status}")

        def _cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", CLOUD_ORIGIN)
            self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")

        def _send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def _valid_origin(self) -> bool:
            return self.headers.get("Origin") == CLOUD_ORIGIN

        def do_OPTIONS(self) -> None:
            if self.path != "/credential" or not self._valid_origin():
                self._send_json(403, {"error": "Browser origin is not permitted."})
                return
            requested_headers = {
                value.strip().lower()
                for value in self.headers.get("Access-Control-Request-Headers", "").split(",")
                if value.strip()
            }
            allowed_headers = {"content-type", "x-shiftline-nonce"}
            if not requested_headers.issubset(allowed_headers):
                self._send_json(403, {"error": "Request headers are not permitted."})
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", CLOUD_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Shiftline-Nonce")
            self.send_header("Access-Control-Max-Age", "60")
            self.send_header("Vary", "Origin")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:
            if self.path != "/credential" or not self._valid_origin():
                self._send_json(403, {"error": "Browser origin is not permitted."})
                return
            supplied_nonce = self.headers.get("X-Shiftline-Nonce", "")
            if not hmac.compare_digest(supplied_nonce, server_nonce):
                self._send_json(403, {"error": "The one-time local connection session is invalid."})
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length < 2 or content_length > 2048:
                    raise ValueError("The local connection received an invalid credential payload.")
                payload = json.loads(self.rfile.read(content_length))
                if not isinstance(payload, dict):
                    raise ValueError("The local connection received an invalid credential payload.")
                api_key = payload.get("api_key")
                if (
                    not isinstance(api_key, str)
                    or len(api_key) > 512
                    or not re.fullmatch(r"hsk_[A-Za-z0-9_-]{20,256}", api_key)
                ):
                    raise ValueError(
                        "No valid Hindsight API key was copied. Generate a new Cloud API key and try again."
                    )

                self._verify_hindsight_key(api_key)
                process = self._start_live_shiftline(api_key)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "provider": "Hindsight",
                        "message": "Hindsight authentication verified. Shiftline is starting.",
                        "app_url": APP_URL,
                        "server_pid": process.pid,
                    },
                )
                threading.Thread(
                    target=self.server.shutdown,
                    name="close-one-time-cloud-handoff",
                    daemon=True,
                ).start()
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:
                self._send_json(
                    502,
                    {
                        "error": (
                            "Hindsight authentication or Shiftline startup failed. "
                            "The credential was not returned to the browser. "
                            f"Provider detail: {exc}"
                        )
                    },
                )

        @staticmethod
        def _verify_hindsight_key(api_key: str) -> None:
            client = Hindsight(base_url=API_URL, api_key=api_key, timeout=15.0)
            try:
                client.get_version()
            finally:
                client.close()

        @staticmethod
        def _start_live_shiftline(api_key: str) -> subprocess.Popen[bytes]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                if probe.connect_ex(("127.0.0.1", APP_PORT)) == 0:
                    raise RuntimeError(
                        f"Port {APP_PORT} is already in use. Close the existing Shiftline server first."
                    )

            python = ROOT / ".venv-hindsight" / "Scripts" / "python.exe"
            if not python.is_file():
                raise RuntimeError("The Shiftline Hindsight Python environment is missing.")

            child_environment = os.environ.copy()
            child_environment.update(
                {
                    "SHIFTLINE_MEMORY_MODE": "hindsight",
                    "HINDSIGHT_API_URL": API_URL,
                    "HINDSIGHT_API_KEY": api_key,
                    "HINDSIGHT_BANK_ID": BANK_ID,
                    "PORT": str(APP_PORT),
                }
            )
            log_path = ROOT / "shiftline-live.log"
            with log_path.open("ab", buffering=0) as log_file:
                process = subprocess.Popen(
                    [str(python), str(ROOT / "server.py")],
                    cwd=str(ROOT),
                    env=child_environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                )

            try:
                for _ in range(20):
                    if process.poll() is not None:
                        raise RuntimeError(
                            f"The Shiftline server exited during startup (exit code {process.returncode})."
                        )
                    try:
                        with urlopen(f"{APP_URL}/api/health", timeout=4) as response:
                            health = json.loads(response.read())
                        if (
                            response.status == 200
                            and health.get("provider") == "Hindsight"
                            and health.get("mode") == "hindsight"
                        ):
                            return process
                    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
                        time.sleep(0.5)
                raise RuntimeError(
                    "The Hindsight key was valid, but Shiftline did not become ready on "
                    f"127.0.0.1:{APP_PORT}. See shiftline-live.log."
                )
            except Exception:
                process.terminate()
                raise

    return CloudCredentialHandler


def main() -> None:
    if sys.version_info < (3, 10):
        raise SystemExit("Connect to Hindsight Cloud with the Python 3.11 environment.")
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-f0-9]{32}", sys.argv[1]):
        raise SystemExit("Pass a fresh 32-character one-time connection token.")
    nonce = sys.argv[1]
    httpd = HTTPServer(("127.0.0.1", 8765), make_handler(nonce))
    timer = threading.Timer(300, httpd.shutdown)
    print("Secure one-time Hindsight Cloud connection bridge started at 127.0.0.1:8765.")
    print("The API key will be transferred directly from the Cloud page into Shiftline memory.")
    print("No key is logged, written to disk, or returned to the browser.")
    print("Waiting up to five minutes for the authenticated Cloud-page handoff.")
    timer.start()
    try:
        httpd.serve_forever(poll_interval=0.25)
    finally:
        timer.cancel()
        httpd.server_close()
    print("One-time Hindsight Cloud connection bridge stopped.")


if __name__ == "__main__":
    main()
