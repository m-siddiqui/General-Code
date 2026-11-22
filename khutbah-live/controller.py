"""Go-live / end logic shared by the web page, the mimbar button and the phone."""

import collections
import os
import subprocess
import threading
import time
from datetime import datetime

from common import BASE_DIR, DATA_DIR, load_state, render_details, save_state
from facebook import Facebook
from obs_control import OBS
from relay import Relay, find_ffmpeg
from youtube import YouTube

# Ignore a "toggle" press that would stop a stream started less than this long ago
# (protects against an accidental double press on a single-button remote).
TOGGLE_GUARD_SECONDS = 60


class Controller:
    def __init__(self, cfg):
        self.cfg = cfg
        self.dry_run = bool(cfg.get("dryRun"))
        self.status = "idle"          # idle | starting | live | stopping
        self.error = ""
        self.session = None
        self._lock = threading.Lock()
        self._stop_requested = False
        self._log = collections.deque(maxlen=60)
        self.relay = Relay(cfg, self.log)
        self.platforms = {}
        if self.dry_run:
            self.platforms = {"youtube": _FakePlatform("youtube"), "facebook": _FakePlatform("facebook")}
            self.obs = _FakeOBS(cfg, self.log)
        else:
            if cfg.get("youtube", {}).get("enabled", True):
                self.platforms["youtube"] = YouTube(cfg)
            if cfg.get("facebook", {}).get("enabled", True):
                self.platforms["facebook"] = Facebook(cfg)
            self.obs = OBS(cfg)
        self._recover()

    # ---- logging & status ------------------------------------------------
    def log(self, msg):
        line = f"{datetime.now().strftime('%H:%M:%S')}  {msg}"
        self._log.append(line)
        print(line, flush=True)

    def next_details(self):
        return load_state().get("next", {})

    def set_next_details(self, details):
        clean = {k: str(details.get(k, "")).strip()[:5000]
                 for k in ("speaker", "topic", "title", "description")}
        state = load_state()
        state["next"] = clean
        save_state(state)
        return clean

    def snapshot(self):
        title, description = render_details(self.cfg, self.next_details())
        session = None
        if self.session:
            session = {k: v for k, v in self.session.items() if k != "ingest"}
        return {
            "status": self.status,
            "error": self.error,
            "dryRun": self.dry_run,
            "session": session,
            "next": self.next_details(),
            "preview": {"title": title, "description": description},
            "platforms": list(self.platforms),
            "history": load_state().get("history", [])[:5],
            "log": list(self._log)[-25:],
        }

    # ---- start ----------------------------------------------------------
    def start(self, source="web"):
        with self._lock:
            if self.status in ("starting", "live"):
                return False, f"Already {self.status}"
            if self.status == "stopping":
                return False, "Still ending the last stream - try again in a few seconds"
            self.status, self.error, self._stop_requested = "starting", "", False
        self.log(f"Go live requested ({source})")
        threading.Thread(target=self._do_start, daemon=True).start()
        return True, "Starting"

    def _do_start(self):
        title, description = render_details(self.cfg, self.next_details())
        session = {"startedAt": time.time(), "title": title, "description": description,
                   "platforms": {}, "ingest": {}}
        try:
            for name, platform in self.platforms.items():
                self.log(f"Creating {name} live event: {title}")
                info = platform.start(title, description)
                session["platforms"][name] = {"id": info["id"], "url": info["url"]}
                session["ingest"][name] = info["ingest"]
            if not session["ingest"]:
                raise RuntimeError("No platforms are enabled in config.json")
            self._persist(session)
            self.relay.start(list(session["ingest"].items()))
            self.log("Starting OBS stream")
            self.obs.start(self.relay.server_url, self.relay.key, self.log)
        except Exception as e:
            self.log(f"Go live FAILED: {e}")
            self._rollback(session)
            with self._lock:
                self.status, self.error = "idle", f"Could not go live: {e}"
            return
        with self._lock:
            self.session, self.status = session, "live"
        self.log("LIVE on " + ", ".join(session["platforms"]))
        threading.Thread(target=self._watch, args=(session,), daemon=True).start()
        if self._stop_requested:
            self.stop("queued")

    def _rollback(self, session):
        self.relay.prepare_stop()
        self.obs.stop()
        self.relay.stop()
        for name, info in session["platforms"].items():
            self.platforms[name].delete(info["id"])
        self._persist(None)

    def _watch(self, session):
        """While live: nudge YouTube live if needed, auto-stop on max duration or if OBS stopped."""
        max_minutes = self.cfg.get("maxDurationMinutes", 90)
        nudged = 0
        obs_off = 0
        while self.session is session and self.status == "live":
            time.sleep(15)
            if self.session is not session or self.status != "live":
                return
            elapsed = time.time() - session["startedAt"]
            yt = session["platforms"].get("youtube")
            if yt and nudged < 3 and elapsed > 25:
                nudged += 1
                try:
                    state = self.platforms["youtube"].ensure_live(yt["id"])
                    if state == "live":
                        nudged = 3
                except Exception as e:
                    self.log(f"YouTube status check: {e}")
            if max_minutes and elapsed > max_minutes * 60:
                self.log(f"Reached the {max_minutes}-minute limit - ending automatically")
                self.stop("time limit")
                return
            streaming = self.obs.is_streaming()
            obs_off = obs_off + 1 if streaming is False else 0
            if obs_off >= 2:
                self.log("OBS is no longer streaming - ending the live events")
                self.stop("OBS stopped")
                return

    # ---- stop -----------------------------------------------------------
    def stop(self, source="web"):
        with self._lock:
            if self.status == "starting":
                self._stop_requested = True
                return True, "Will end as soon as it has started"
            if self.status != "live":
                return False, f"Not live (currently {self.status})"
            self.status = "stopping"
            session = self.session
        self.log(f"End requested ({source})")
        threading.Thread(target=self._do_stop, args=(session,), daemon=True).start()
        return True, "Ending"

    def toggle(self, source="button"):
        if self.status == "live" and self.session:
            if time.time() - self.session["startedAt"] < TOGGLE_GUARD_SECONDS:
                return False, "Ignored: stream started less than a minute ago"
            return self.stop(source)
        return self.start(source)

    def _do_stop(self, session):
        self.relay.prepare_stop()
        self.obs.stop()
        self.relay.stop()
        for name, info in session["platforms"].items():
            try:
                self.platforms[name].end(info["id"])
            except Exception as e:
                self.log(f"Ending {name}: {e}")
        state = load_state()
        history = state.get("history", [])
        history.insert(0, {
            "title": session["title"],
            "startedAt": session["startedAt"],
            "minutes": round((time.time() - session["startedAt"]) / 60),
            "links": {k: v["url"] for k, v in session["platforms"].items()},
        })
        state["history"] = history[:20]
        state["next"] = {}       # this week's speaker/topic shouldn't leak into next week
        state["active"] = None
        save_state(state)
        with self._lock:
            self.session, self.status = None, "idle"
        self.log("Ended. Recordings stay on YouTube and Facebook.")

    # ---- crash recovery ---------------------------------------------------
    def _persist(self, session):
        state = load_state()
        state["active"] = session
        save_state(state)

    def _recover(self):
        """If this app restarted mid-khutbah, bring the relay back so OBS can reconnect."""
        session = load_state().get("active")
        if not session:
            return
        self.log("Recovering a live session that was running before a restart")
        self.session, self.status = session, "live"
        try:
            self.relay.start(list(session["ingest"].items()))
        except Exception as e:
            self.log(f"Could not restart relay: {e}")
        threading.Thread(target=self._watch, args=(session,), daemon=True).start()


# ---- dry-run fakes: exercise the whole flow without touching YouTube/Facebook --------------
class _FakePlatform:
    def __init__(self, name):
        self.name = name

    def start(self, title, description):
        out = os.path.join(DATA_DIR, "dryrun")
        os.makedirs(out, exist_ok=True)
        return {"id": f"dry-{self.name}-{int(time.time())}",
                "ingest": os.path.join(out, f"{self.name}.flv"),
                "url": f"https://example.invalid/{self.name}"}

    def ensure_live(self, _id):
        return "live"

    def end(self, _id):
        pass

    def delete(self, _id):
        pass


class _FakeOBS:
    """Pushes a test pattern into the relay, standing in for OBS."""

    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.proc = None

    def start(self, server, key, log):
        ffmpeg = find_ffmpeg(self.cfg.get("relay", {}).get("ffmpegPath"))
        self.proc = subprocess.Popen([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-re",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440",
            "-c:v", "libx264", "-preset", "ultrafast", "-g", "60", "-c:a", "aac",
            "-f", "flv", f"{server}/{key}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=BASE_DIR)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=10)

    def is_streaming(self):
        return bool(self.proc and self.proc.poll() is None)
