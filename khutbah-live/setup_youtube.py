#!/usr/bin/env python3
"""One-time: connect the masjid's YouTube channel.  python3 setup_youtube.py

You need an OAuth client of type "Desktop app" from Google Cloud (see README).
A browser window opens; sign in with the account that owns the YouTube channel.
"""

import getpass
import http.server
import secrets
import threading
import urllib.parse
import webbrowser

from common import http
from youtube import SCOPE, TOKEN_URL, save_client


def main():
    print("Paste the OAuth client details from Google Cloud (Credentials -> your Desktop client).")
    client_id = input("Client ID: ").strip()
    client_secret = getpass.getpass("Client secret (hidden): ").strip()

    state = secrets.token_urlsafe(16)
    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state:
                result.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Done - you can close this tab and go back to the Terminal.</h2>")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    server = http.server.HTTPServer(("127.0.0.1", 0), Callback)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    print("\nOpening your browser. If it doesn't open, visit:\n" + url + "\n")
    webbrowser.open(url)
    server.serve_forever()

    if "code" not in result:
        raise SystemExit(f"Sign-in did not complete: {result.get('error', 'no code returned')}")
    tokens = http("POST", TOKEN_URL, form={
        "code": result["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    })
    if "refresh_token" not in tokens:
        raise SystemExit("Google did not return a refresh token. Remove the app's access at "
                         "myaccount.google.com/permissions and run this again.")
    save_client(client_id, client_secret, tokens["refresh_token"])

    channel = http("GET", "https://www.googleapis.com/youtube/v3/channels",
                   params={"part": "snippet", "mine": "true"},
                   headers={"Authorization": f"Bearer {tokens['access_token']}"})
    names = [c["snippet"]["title"] for c in channel.get("items", [])]
    print(f"YouTube connected: {', '.join(names) or '(no channel found on this account!)'}")


if __name__ == "__main__":
    main()
