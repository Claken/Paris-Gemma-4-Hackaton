"""Interface web locale, sans dépendance externe, pour la démo."""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent import AgentError, process, transcribe_audio

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "static" / "index.html"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 6 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "DroitDeRetard/0.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - API imposée par BaseHTTPRequestHandler
        if self.path not in {"/", "/index.html"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = INDEX.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - API imposée par BaseHTTPRequestHandler
        if self.path not in {"/api/analyze", "/api/transcribe"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            max_request_bytes = (
                MAX_AUDIO_BYTES if self.path == "/api/transcribe" else MAX_UPLOAD_BYTES
            ) * 2
            if length <= 0 or length > max_request_bytes:
                raise AgentError("Requête vide ou trop volumineuse.")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/transcribe":
                try:
                    audio = base64.b64decode(
                        payload.get("audio_base64", ""), validate=True
                    )
                except (binascii.Error, ValueError) as exc:
                    raise AgentError("Enregistrement audio invalide.") from exc
                if not audio or len(audio) > MAX_AUDIO_BYTES:
                    raise AgentError(
                        "L'enregistrement doit peser moins de 6 Mo."
                    )
                self._send_json(
                    HTTPStatus.OK,
                    {"transcription": transcribe_audio(audio)},
                )
                return

            filename = Path(str(payload.get("filename", ""))).name
            suffix = Path(filename).suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                raise AgentError("Format accepté : PDF, PNG, JPG, JPEG ou WEBP.")
            try:
                content = base64.b64decode(
                    payload.get("file_base64", ""), validate=True
                )
            except (binascii.Error, ValueError) as exc:
                raise AgentError("Fichier encodé invalide.") from exc
            if not content or len(content) > MAX_UPLOAD_BYTES:
                raise AgentError("Le fichier doit peser moins de 10 Mo.")

            with tempfile.TemporaryDirectory(prefix="droit-retard-upload-") as folder:
                document = Path(folder) / f"document{suffix}"
                document.write_bytes(content)
                result = process(
                    document,
                    str(payload.get("incident", "")).strip() or None,
                    confirmed_booking_reference=(
                        str(payload.get("booking_reference", "")).strip() or None
                    ),
                )
            result["document"] = filename
            self._send_json(HTTPStatus.OK, result)
        except (AgentError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Erreur interne. Consulte le terminal de l'application."},
            )

    def log_message(self, message: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {message % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interface Droit de Retard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=7865, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"Droit de Retard disponible sur http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt de l'application.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
