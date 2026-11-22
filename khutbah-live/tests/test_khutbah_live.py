"""Run from the khutbah-live folder:  python3 -m unittest discover tests -v"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from common import render_details  # noqa: E402

CFG = json.load(open(os.path.join(HERE, "config.example.json")))


class RenderTests(unittest.TestCase):
    now = datetime(2026, 11, 27, 13, 15)

    def test_full_details(self):
        title, desc = render_details(CFG, {"speaker": "Imam Abdullah", "topic": "Gratitude"}, self.now)
        self.assertEqual(title, "Jumu'ah Khutbah | Gratitude | Imam Abdullah | 27 November 2026")
        self.assertIn("Speaker: Imam Abdullah", desc)
        self.assertIn("Topic: Gratitude", desc)

    def test_empty_details_drop_parts_and_lines(self):
        title, desc = render_details(CFG, {}, self.now)
        self.assertEqual(title, "Jumu'ah Khutbah | 27 November 2026")
        self.assertNotIn("Speaker:", desc)
        self.assertNotIn("Topic:", desc)
        self.assertIn("27 November 2026", desc)

    def test_overrides_and_youtube_limits(self):
        title, desc = render_details(CFG, {"title": "<b>" + "x" * 200, "description": "a <tag> b"}, self.now)
        self.assertEqual(len(title), 100)
        self.assertNotIn("<", title)
        self.assertEqual(desc, "a tag b")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class DryRunEndToEnd(unittest.TestCase):
    """Full go-live / end cycle with fake platforms and a test-pattern 'OBS'."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for name in os.listdir(HERE):
            if name.endswith(".py") or name == "static":
                src = os.path.join(HERE, name)
                (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(self.dir, name))
        self.port = free_port()
        cfg = dict(CFG, accessKey="test-key-123", listenHost="127.0.0.1", listenPort=self.port, dryRun=True,
                   relay={"port": free_port(), "backupDir": "recordings"})
        json.dump(cfg, open(os.path.join(self.dir, "config.json"), "w"))
        self.proc = subprocess.Popen([sys.executable, "server.py"], cwd=self.dir,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(50):
            try:
                self.api("status")
                break
            except Exception:
                time.sleep(0.1)

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait()
        subprocess.run(["pkill", "-f", self.dir], check=False)
        shutil.rmtree(self.dir, ignore_errors=True)

    def api(self, action, body=None, key="test-key-123"):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/{action}", method="POST" if body is not None else "GET",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Access-Key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def wait_for(self, status, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, s = self.api("status")
            if s["status"] == status:
                return s
            time.sleep(0.3)
        self.fail(f"never reached {status}: {s}")

    def test_wrong_key_rejected(self):
        code, _ = self.api("start", {}, key="nope")
        self.assertEqual(code, 401)

    def test_full_cycle(self):
        _, s = self.api("next", {"speaker": "Sh. Test", "topic": "Patience"})
        self.assertIn("Patience", s["preview"]["title"])

        code, r = self.api("start", {})
        self.assertEqual(code, 200, r)
        s = self.wait_for("live")
        self.assertIn("Sh. Test", s["session"]["title"])
        self.assertNotIn("ingest", s["session"])  # stream keys never leave the Mac

        code, r = self.api("toggle", {})          # accidental double press: ignored
        self.assertEqual(code, 409)
        self.assertIn("Ignored", r["message"])

        dry = os.path.join(self.dir, "data", "dryrun")
        rec = os.path.join(self.dir, "recordings")
        outputs = [os.path.join(dry, "youtube.flv"), os.path.join(dry, "facebook.flv")]
        deadline = time.time() + 25
        while time.time() < deadline:
            backups = [os.path.join(rec, f) for f in os.listdir(rec)] if os.path.isdir(rec) else []
            if backups and all(os.path.exists(p) and os.path.getsize(p) > 0 for p in outputs + backups):
                break
            time.sleep(0.5)
        else:
            self.fail("relay never wrote to every destination")

        code, _ = self.api("stop", {})
        self.assertEqual(code, 200)
        s = self.wait_for("idle")
        self.assertEqual(s["history"][0]["title"], "Jumu'ah Khutbah | Patience | Sh. Test | "
                         + datetime.now().strftime("%d %B %Y").lstrip("0"))
        self.assertEqual(s["next"], {})           # cleared for next week

        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              os.path.join(dry, "youtube.flv")], capture_output=True, text=True).stdout
        self.assertGreater(float(out), 3)


if __name__ == "__main__":
    unittest.main()
