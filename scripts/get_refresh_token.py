"""One-time OAuth 2.0 setup helper.

Run this locally to obtain a refresh token for the YouTube Data API.
Requires YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env or as env vars.

Usage:
    python scripts/get_refresh_token.py
"""

import http.server
import json
import os
import threading
import urllib.parse
import urllib.request
import webbrowser

from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
REDIRECT_URI = "http://localhost:8090"
SCOPES = "https://www.googleapis.com/auth/youtube"

auth_code: str | None = None
server_ready = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        auth_code = params.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Authorization complete. You can close this tab.</h1>")

    def log_message(self, format, *args) -> None:
        pass


def main() -> None:
    global auth_code

    server = http.server.HTTPServer(("localhost", 8090), CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        })
    )

    print(f"\nOpening browser for authorization...\n{auth_url}\n")
    webbrowser.open(auth_url)

    thread.join(timeout=120)
    server.server_close()

    if not auth_code:
        print("ERROR: No authorization code received.")
        return

    token_data = urllib.parse.urlencode({
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=token_data)
    with urllib.request.urlopen(req) as resp:
        tokens = json.loads(resp.read())

    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        print(f"\nYOUTUBE_REFRESH_TOKEN={refresh_token}\n")
        print("Add this to your .env file.")
    else:
        print("\nERROR: No refresh token in response. Try revoking access and re-running.")
        print(json.dumps(tokens, indent=2))


if __name__ == "__main__":
    main()
