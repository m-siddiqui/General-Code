"""Shared helpers: paths, config/secret/state files, HTTP calls, title rendering."""

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SECRETS_PATH = os.path.join(DATA_DIR, "secrets.json")
STATE_PATH = os.path.join(DATA_DIR, "state.json")

_file_lock = threading.Lock()


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _write_json(path, data, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_config():
    cfg = _read_json(CONFIG_PATH, None)
    if cfg is None:
        raise SystemExit(
            "config.json not found. Copy config.example.json to config.json and edit it."
        )
    return cfg


def load_secrets():
    with _file_lock:
        return _read_json(SECRETS_PATH, {})


def update_secrets(**values):
    with _file_lock:
        data = _read_json(SECRETS_PATH, {})
        data.update(values)
        _write_json(SECRETS_PATH, data, private=True)


def load_state():
    with _file_lock:
        return _read_json(STATE_PATH, {})


def save_state(state):
    with _file_lock:
        _write_json(STATE_PATH, state)


class HttpError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def http(method, url, params=None, json_body=None, form=None, headers=None, timeout=30):
    """Small JSON-over-HTTP helper. Returns parsed JSON (or {} for empty bodies)."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = None
    headers = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode(errors="replace")) from None
    return json.loads(raw) if raw.strip() else {}


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _fill(text, values):
    """Fill {name} placeholders. Returns None if any placeholder used is empty."""
    missing = False

    def sub(m):
        nonlocal missing
        val = values.get(m.group(1), "")
        if not val:
            missing = True
        return val

    out = _PLACEHOLDER.sub(sub, text)
    return None if missing else out


def render_details(cfg, details, now=None):
    """Build (title, description) from the templates in config and this week's details.

    Title: `titleParts` are joined with `titleSeparator`; parts whose placeholders
    are empty are left out. Description: lines whose placeholders are empty are left out.
    An explicit title/description in `details` overrides the template.
    """
    now = now or datetime.now()
    values = {
        "speaker": (details.get("speaker") or "").strip(),
        "topic": (details.get("topic") or "").strip(),
        "date": now.strftime(cfg.get("dateFormat", "%d %B %Y")).lstrip("0"),
    }
    tpl = cfg["templates"]

    title = (details.get("title") or "").strip()
    if not title:
        parts = [_fill(p, values) for p in tpl["titleParts"]]
        title = tpl.get("titleSeparator", " | ").join(p for p in parts if p)

    description = (details.get("description") or "").strip()
    if not description:
        lines = [_fill(line, values) for line in tpl["descriptionLines"]]
        description = "\n".join(line for line in lines if line is not None).strip()

    # YouTube rejects < and > and limits the title to 100 characters.
    title = title.replace("<", "").replace(">", "")[:100]
    description = description.replace("<", "").replace(">", "")[:5000]
    return title, description
