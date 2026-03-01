"""
One-time script to generate a Kite access token.
Run this each morning before starting the tracker.

Usage:
    python get_token.py
"""

import os
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
CALLBACK_PORT = 7676

if not API_KEY or not API_SECRET:
    print("Error: Set KITE_API_KEY and KITE_API_SECRET in your .env file first.")
    raise SystemExit(1)

request_token_holder = {}
server_ready = threading.Event()


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "request_token" in params:
            request_token_holder["token"] = params["request_token"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:sans-serif;text-align:center;margin-top:80px">
                <h2>&#10003; Login successful!</h2>
                <p>Access token generated. You can close this tab.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing request_token.")

    def log_message(self, format, *args):
        pass  # suppress server logs


def start_server():
    server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    server_ready.set()
    server.handle_request()  # handle exactly one request then stop
    server.server_close()


# Start callback server in background
thread = threading.Thread(target=start_server, daemon=True)
thread.start()
server_ready.wait()

kite = KiteConnect(api_key=API_KEY)
login_url = kite.login_url()

print(f"Opening Kite login in your browser...")
print(f"Login URL: {login_url}\n")
webbrowser.open(login_url)
print(f"Waiting for Kite to redirect to http://localhost:{CALLBACK_PORT}/api/callback ...")

thread.join(timeout=120)

if "token" not in request_token_holder:
    print("\nError: Timed out waiting for login. Please try again.")
    raise SystemExit(1)

request_token = request_token_holder["token"]
print(f"Got request_token: {request_token[:8]}...")

data = kite.generate_session(request_token, api_secret=API_SECRET)
access_token = data["access_token"]

set_key(".env", "KITE_ACCESS_TOKEN", access_token)

print(f"Access token saved to .env: {access_token[:8]}...{access_token[-4:]}")
print("\nDone! You can now run:  python tracker.py")
