"""Local relay: OBS streams once to ffmpeg on this Mac, ffmpeg copies it to every platform.

Copying (no re-encoding) costs almost no CPU. If one platform drops, the others keep going;
the relay is then restarted (OBS reconnects by itself) so the dropped platform is retried.
"""

import os
import shutil
import subprocess
import threading
import time


def find_ffmpeg(configured=None):
    for candidate in (configured, "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", shutil.which("ffmpeg")):
        if candidate and os.path.exists(candidate):
            return candidate
    raise RuntimeError("ffmpeg not found. Install it with: brew install ffmpeg")


def _tee_escape(url):
    return url.replace("\\", "\\\\").replace("|", "\\|")


class Relay:
    RETRY_GAP = 60     # seconds between restarts caused by a dropped platform
    MAX_RETRIES = 5

    def __init__(self, cfg, log):
        rcfg = cfg.get("relay", {})
        self.port = rcfg.get("port", 1935)
        self.key = "khutbah"
        self.server_url = f"rtmp://127.0.0.1:{self.port}/live"
        self.ffmpeg = rcfg.get("ffmpegPath")
        self.backup_dir = rcfg.get("backupDir")
        self.log = log
        self._proc = None
        self._running = False
        self._thread = None
        self._targets = []
        self._retries = 0
        self._last_restart = 0.0
        self._segment = 0
        self._stamp = ""

    def _command(self):
        slaves = [f"[f=flv:flvflags=no_duration_filesize:onfail=ignore]{_tee_escape(url)}"
                  for _, url in self._targets]
        if self.backup_dir:
            os.makedirs(self.backup_dir, exist_ok=True)
            self._segment += 1
            suffix = "" if self._segment == 1 else f"-part{self._segment}"
            path = os.path.join(self.backup_dir, f"khutbah-{self._stamp}{suffix}.mkv")
            slaves.append(f"[f=matroska:onfail=ignore]{_tee_escape(path)}")
        return [
            self.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning",
            "-listen", "1", "-i", f"{self.server_url}/{self.key}",
            "-map", "0", "-c", "copy", "-f", "tee", "|".join(slaves),
        ]

    def start(self, targets):
        """targets: list of (name, rtmp_url)."""
        self.ffmpeg = find_ffmpeg(self.ffmpeg)
        self._targets = targets
        self._retries = 0
        self._segment = 0
        self._stamp = time.strftime("%Y-%m-%d_%H%M")
        self._running = True
        self._thread = threading.Thread(target=self._supervise, daemon=True)
        self._thread.start()
        time.sleep(1.5)  # let ffmpeg start listening before OBS connects

    def _supervise(self):
        while self._running:
            self._proc = subprocess.Popen(self._command(), stderr=subprocess.PIPE,
                                          stdout=subprocess.DEVNULL, text=True, bufsize=1)
            refused = False
            for line in self._proc.stderr:
                line = line.strip()
                if not line:
                    continue
                if "error opening" in line:
                    refused = True  # rejected at connect: retrying won't help, don't disturb the others
                    self.log(f"Relay: a platform refused the connection ({line})")
                elif "Slave muxer" in line and "failed" in line:
                    if refused:
                        refused = False
                        continue
                    self.log(f"Relay: a platform connection dropped ({line})")
                    self._maybe_retry()
                elif "error" in line.lower() and "demux" not in line.lower():
                    self.log(f"Relay: {line}")
            self._proc.wait()
            if self._running:
                self.log("Relay restarted - OBS will reconnect automatically")
                time.sleep(0.5)

    def _maybe_retry(self):
        now = time.time()
        if self._retries >= self.MAX_RETRIES or now - self._last_restart < self.RETRY_GAP:
            return
        self._retries += 1
        self._last_restart = now
        # Give OBS a few seconds, then restart so the dropped platform reconnects.
        threading.Timer(5, self._kill).start()

    def _kill(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def prepare_stop(self):
        """Call before stopping OBS so the relay isn't restarted when OBS disconnects."""
        self._running = False

    def stop(self):
        self._running = False
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.wait(timeout=10)  # normally exits by itself once OBS stops
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
