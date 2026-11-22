"""YouTube Live: create a broadcast with title/description, bind it to a reusable stream, end it."""

import time
from datetime import datetime, timezone

from common import http, load_secrets, load_state, save_state, update_secrets

API = "https://www.googleapis.com/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


class YouTube:
    def __init__(self, cfg):
        self.cfg = cfg.get("youtube", {})
        self._token = None
        self._token_expiry = 0

    def _access_token(self):
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        s = load_secrets()
        if not s.get("youtube_refresh_token"):
            raise RuntimeError("YouTube is not connected yet. Run: python3 setup_youtube.py")
        resp = http("POST", TOKEN_URL, form={
            "client_id": s["youtube_client_id"],
            "client_secret": s["youtube_client_secret"],
            "refresh_token": s["youtube_refresh_token"],
            "grant_type": "refresh_token",
        })
        self._token = resp["access_token"]
        self._token_expiry = time.time() + int(resp.get("expires_in", 3600))
        return self._token

    def _call(self, method, path, params=None, body=None):
        return http(method, f"{API}/{path}", params=params, json_body=body,
                    headers={"Authorization": f"Bearer {self._access_token()}"})

    def _ingest_url(self):
        """Return the RTMP URL of our reusable stream, creating the stream the first time."""
        state = load_state()
        stream_id = state.get("youtube_stream_id")
        item = None
        if stream_id:
            items = self._call("GET", "liveStreams", {"part": "id,cdn", "id": stream_id}).get("items", [])
            item = items[0] if items else None
        if item is None:
            item = self._call("POST", "liveStreams", {"part": "snippet,cdn,contentDetails"}, {
                "snippet": {"title": "Khutbah Live (reusable)"},
                "cdn": {"ingestionType": "rtmp", "resolution": "variable", "frameRate": "variable"},
                "contentDetails": {"isReusable": True},
            })
            state = load_state()
            state["youtube_stream_id"] = item["id"]
            save_state(state)
        info = item["cdn"]["ingestionInfo"]
        return item["id"], f"{info['ingestionAddress']}/{info['streamName']}"

    def start(self, title, description):
        """Create a broadcast that goes live by itself when video arrives. Returns session info."""
        stream_id, ingest = self._ingest_url()
        bc = self._call("POST", "liveBroadcasts", {"part": "snippet,status,contentDetails"}, {
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            "status": {
                "privacyStatus": self.cfg.get("privacy", "public"),
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,
                "enableDvr": True,
                "recordFromStart": True,
                "latencyPreference": "normal",
            },
        })
        try:
            self._call("POST", "liveBroadcasts/bind",
                       {"id": bc["id"], "part": "id,contentDetails", "streamId": stream_id})
            if self.cfg.get("playlistId"):
                try:
                    self._call("POST", "playlistItems", {"part": "snippet"}, {"snippet": {
                        "playlistId": self.cfg["playlistId"],
                        "resourceId": {"kind": "youtube#video", "videoId": bc["id"]},
                    }})
                except Exception:
                    pass  # A playlist problem should never stop the khutbah going live.
        except Exception:
            self.delete(bc["id"])
            raise
        return {"id": bc["id"], "ingest": ingest, "url": f"https://youtu.be/{bc['id']}"}

    def ensure_live(self, broadcast_id):
        """If auto-start didn't fire, push the broadcast live ourselves. Safe to call repeatedly."""
        items = self._call("GET", "liveBroadcasts", {"part": "status", "id": broadcast_id}).get("items", [])
        if items and items[0]["status"]["lifeCycleStatus"] in ("ready", "testing"):
            self._call("POST", "liveBroadcasts/transition",
                       {"id": broadcast_id, "broadcastStatus": "live", "part": "status"})
        return items[0]["status"]["lifeCycleStatus"] if items else "missing"

    def end(self, broadcast_id):
        try:
            self._call("POST", "liveBroadcasts/transition",
                       {"id": broadcast_id, "broadcastStatus": "complete", "part": "status"})
        except Exception:
            pass  # Already completed by auto-stop, or never went live.

    def delete(self, broadcast_id):
        try:
            self._call("DELETE", "liveBroadcasts", {"id": broadcast_id})
        except Exception:
            pass


def save_client(client_id, client_secret, refresh_token):
    update_secrets(youtube_client_id=client_id, youtube_client_secret=client_secret,
                   youtube_refresh_token=refresh_token)
