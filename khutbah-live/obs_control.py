"""Drive OBS over its built-in WebSocket server: point it at the local relay, start/stop streaming."""

import subprocess
import time


class OBS:
    def __init__(self, cfg):
        self.cfg = cfg.get("obs", {})

    def _client(self):
        import obsws_python  # imported lazily so dry-run mode doesn't need it

        return obsws_python.ReqClient(
            host=self.cfg.get("host", "localhost"),
            port=self.cfg.get("port", 4455),
            password=self.cfg.get("password", ""),
            timeout=5,
        )

    def connect(self, log):
        """Connect, opening OBS first if it isn't running and `launchIfClosed` is set."""
        try:
            return self._client()
        except Exception:
            if not self.cfg.get("launchIfClosed", True):
                raise RuntimeError("Can't reach OBS. Is it open with the WebSocket server enabled?")
        log("OBS isn't reachable - opening it")
        subprocess.run(["open", "-a", self.cfg.get("appName", "OBS")], check=False)
        deadline = time.time() + 45
        while time.time() < deadline:
            time.sleep(3)
            try:
                client = self._client()
                time.sleep(5)  # give the IP camera source a moment to connect
                return client
            except Exception:
                pass
        raise RuntimeError("OBS didn't come up. Is the WebSocket server enabled in OBS?")

    def start(self, relay_server, relay_key, log):
        client = self.connect(log)
        if client.get_stream_status().output_active:
            client.stop_stream()
            time.sleep(3)
        client.set_stream_service_settings("rtmp_custom", {
            "server": relay_server, "key": relay_key, "use_auth": False,
        })
        client.start_stream()

    def stop(self):
        try:
            client = self._client()
            if client.get_stream_status().output_active:
                client.stop_stream()
        except Exception:
            pass

    def is_streaming(self):
        try:
            return bool(self._client().get_stream_status().output_active)
        except Exception:
            return None
