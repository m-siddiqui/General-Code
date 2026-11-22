"""Facebook Page Live: create a live video with title/description, then end it."""

from common import http, load_secrets


class Facebook:
    def __init__(self, cfg):
        self.version = cfg.get("facebook", {}).get("graphApiVersion", "v25.0")
        self.base = f"https://graph.facebook.com/{self.version}"

    def _creds(self):
        s = load_secrets()
        if not s.get("facebook_page_token"):
            raise RuntimeError("Facebook is not connected yet. Run: python3 setup_facebook.py")
        return s["facebook_page_id"], s["facebook_page_token"]

    def start(self, title, description):
        page_id, token = self._creds()
        live = http("POST", f"{self.base}/{page_id}/live_videos", form={
            "status": "LIVE_NOW",
            "title": title,
            "description": description,
            "access_token": token,
        })
        try:
            info = http("GET", f"{self.base}/{live['id']}", params={
                "fields": "secure_stream_url,stream_url,permalink_url,video",
                "access_token": token,
            })
        except Exception:
            self.delete(live["id"])
            raise
        ingest = info.get("secure_stream_url") or live.get("secure_stream_url") or info.get("stream_url")
        permalink = info.get("permalink_url", "")
        if permalink.startswith("/"):
            permalink = "https://www.facebook.com" + permalink
        return {"id": live["id"], "ingest": ingest, "url": permalink or f"https://www.facebook.com/{page_id}/live"}

    def end(self, live_id):
        _, token = self._creds()
        try:
            http("POST", f"{self.base}/{live_id}", form={"end_live_video": "true", "access_token": token})
        except Exception:
            pass  # Already ended (e.g. Facebook ended it when the video stopped).

    def delete(self, live_id):
        try:
            _, token = self._creds()
            http("DELETE", f"{self.base}/{live_id}", params={"access_token": token})
        except Exception:
            pass
