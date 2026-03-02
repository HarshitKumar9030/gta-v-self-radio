"""
Local HTTP callback server for Spotify OAuth2.
Spotify allows http://localhost as a special case for development.
Includes a manual URL-paste fallback if the auto-capture fails.
"""

from __future__ import annotations

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import urlparse, parse_qs

from rich.console import Console

console = Console()


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback code."""

    auth_code: Optional[str] = None
    error: Optional[str] = None
    _got_callback = threading.Event()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self._send_success_page()
            _CallbackHandler._got_callback.set()
        elif "error" in params:
            _CallbackHandler.error = params["error"][0]
            self._send_error_page(params["error"][0])
            _CallbackHandler._got_callback.set()
        else:
            # Ignore unrelated requests (favicon, etc.) — keep listening
            self.send_response(204)
            self.end_headers()

    def _send_success_page(self) -> None:
        html = """
        <html><body style="background:#1DB954;color:white;display:flex;
        justify-content:center;align-items:center;height:100vh;
        font-family:sans-serif;margin:0">
        <div style="text-align:center">
        <h1>&#10003; Authenticated!</h1>
        <p>You can close this tab and return to the terminal.</p>
        </div></body></html>
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _send_error_page(self, error: str) -> None:
        html = f"""
        <html><body style="background:#e74c3c;color:white;display:flex;
        justify-content:center;align-items:center;height:100vh;
        font-family:sans-serif;margin:0">
        <div style="text-align:center">
        <h1>&#10007; Authentication Failed</h1>
        <p>{error}</p>
        </div></body></html>
        """
        self.send_response(400)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args) -> None:
        """Suppress default HTTP logging."""
        pass


def wait_for_callback(port: int = 8888, timeout: int = 120) -> Optional[str]:
    """
    Start a local HTTP server on localhost, wait for the OAuth callback.
    Returns the auth code, or None on timeout/error.
    """
    # Reset state
    _CallbackHandler.auth_code = None
    _CallbackHandler.error = None
    _CallbackHandler._got_callback.clear()

    server = HTTPServer(("localhost", port), _CallbackHandler)
    server.timeout = 1  # 1-second poll so we can check the event

    def _serve() -> None:
        """Keep handling requests until we get the callback or are told to stop."""
        while not _CallbackHandler._got_callback.is_set():
            server.handle_request()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    # Wait for the callback (with timeout)
    got_it = _CallbackHandler._got_callback.wait(timeout=timeout)

    server.server_close()

    if _CallbackHandler.error:
        console.print(f"[bold red]OAuth error:[/] {_CallbackHandler.error}")
        return None

    if not got_it:
        return None  # timed out

    return _CallbackHandler.auth_code


def extract_code_from_url(url: str) -> Optional[str]:
    """Extract the 'code' parameter from a pasted callback URL."""
    try:
        parsed = urlparse(url.strip())
        params = parse_qs(parsed.query)
        codes = params.get("code", [])
        return codes[0] if codes else None
    except Exception:
        return None
