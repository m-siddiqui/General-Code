# Project memory: Khutbah Live (ISNWO)

Hand-off notes from the cloud session that built this app, for continuing in a local Claude
session on the Mac Studio. Paste this into the new session (or point it at this file).

## The goal
- ISNWO (a masjid) live streams the Jumu'ah khutbah. An IP camera is a source in **OBS Studio on a Mac Studio**.
- **Old workflow:** record manually in OBS, trim to the khutbah in CapCut, upload by hand to Facebook and YouTube.
- **Wanted:** stream live to **YouTube and the ISNWO Facebook Page** at once, with a title and description set beforehand.
  Start and stop it remotely, so that when the stream ends the video is already on both platforms. Free if possible.
- **Owner's answers:** the Facebook destination is a **Page**. The title and description change each week (speaker/topic).
  They want control from **both** a phone (remotely) and a **simple physical button at the mimbar** (e.g. Bluetooth).

## What was built (branch `claude/khutbah-live-stream-setup-n7wqqa`, folder `khutbah-live/`)
Python 3 (stdlib only + `obsws-python`, which the owner had already used in `obs-scheduled-recording/`). Zero other deps.

| File | Role |
|---|---|
| `server.py` | HTTP server (default port 8080). Serves the phone page and `/api/status`, `/api/next`, `/api/start`, `/api/stop`, `/api/toggle`. All `/api/*` calls need `accessKey`, sent as the `X-Access-Key` header or `?key=`. GET and POST both work, for simple buttons. |
| `controller.py` | State machine idle → starting → live → stopping. Creates the platform events, starts the relay, drives OBS. Rolls back on failure. Watchdog: nudges YouTube live if auto-start didn't fire, auto-ends after `maxDurationMinutes`, ends if OBS stops streaming. Crash recovery from `data/state.json`. `toggle` ignores presses in the first 60 s of a stream. `dryRun` mode uses fake platforms plus an ffmpeg test pattern in place of OBS. |
| `youtube.py` | OAuth refresh-token flow. Reuses one `liveStream` (id saved in state). Each week: `liveBroadcasts.insert` (enableAutoStart/Stop, recordFromStart, privacy from config), bind, optional playlist insert. On stop it transitions the broadcast to `complete`. |
| `facebook.py` | Graph API (default **v25.0**): `POST /{page}/live_videos status=LIVE_NOW` with title/description, read `secure_stream_url` and permalink. On stop: `end_live_video=true`. |
| `obs_control.py` | Uses OBS WebSocket (OBS 28+). Opens OBS with `open -a OBS` if it isn't reachable. Sets the stream service to custom `rtmp://127.0.0.1:1935/live`, key `khutbah`. Then start/stop. |
| `relay.py` | `ffmpeg -listen 1` receives OBS's RTMP and `-c copy` → `tee` muxer to every platform, plus an mkv backup in `recordings/`. Each output has `onfail=ignore`. A platform that refuses the connection is just dropped. A platform that drops mid-stream triggers a relay restart (max 5, at least 60 s apart), and OBS's auto-reconnect resumes the stream. |
| `common.py` | Config/secrets/state files, HTTP helper, and title/description templating. Title = `titleParts` joined by ` \| `, leaving out parts whose `{speaker}`/`{topic}` are empty. Description = lines, leaving out lines with empty placeholders. YouTube limits enforced: 100-character title, no `<` or `>`. |
| `setup_youtube.py` | One-time loopback OAuth (Desktop client) → refresh token in `data/secrets.json` (chmod 600). |
| `setup_facebook.py` | One-time: App ID + secret + short-lived user token from Graph API Explorer → long-lived token → non-expiring **Page** token. Checks the permissions. |
| `static/index.html` | Mobile control page: status, Go Live / End (End asks for confirmation), this week's speaker/topic form, title preview, links, history and log. Light and dark mode. |
| `macos/install-autostart.sh` | LaunchAgent `org.isnwo.khutbah-live`: starts at login, KeepAlive, wrapped in `caffeinate -i`, logs to `data/server.log`. |
| `macos/hammerspoon-init.lua` | Optional: Bluetooth clicker (Page Down / Page Up) → start/stop. |
| `tests/test_khutbah_live.py` | Template unit tests plus a full dry-run end-to-end test (needs ffmpeg). Run: `python3 -m unittest discover tests -v`. |
| `README.md` | Full setup guide and weekly use, written for the masjid volunteer. |

Gitignored: `config.json`, `data/` (secrets, state, logs), `recordings/`.

## Decisions and why
- **ffmpeg tee relay instead of an OBS multistream plugin:** a plugin's outputs can't be set or started through obs-websocket, and the app needs fresh ingest URLs each week. ffmpeg copies the stream without re-encoding, which costs almost no CPU.
- **MediaMTX was considered but not used.** It would allow a separate reconnect per platform, but the cloud sandbox blocked downloading its binary, so the design that could be tested (ffmpeg only) was chosen. It could be revisited on the Mac with `brew install mediamtx` if per-platform reconnects matter.
- **Facebook goes live immediately (`LIVE_NOW`) rather than being pre-scheduled.** The phone page holds the title in advance instead.
- **Speaker and topic are cleared after each stream** so they don't carry over to the next week.
- **Separate start/stop actions are recommended for the button** (click = start, hold = stop), so an accidental tap can't end the stream.

## Facts checked against the docs (Nov 2026)
- Facebook **Page** live needs a Page token with `pages_read_engagement` and `pages_manage_posts`. `publish_video` is only needed for User broadcasts. Also request `pages_show_list` for `/me/accounts`.
- The Graph API is at v25/v26. The default is v25.0 (configurable).
- Google OAuth apps left in **"Testing"** have refresh tokens that expire after 7 days. The app must be **published ("In production")**. Verification isn't needed for own use; the user clicks past the "unverified app" warning.
- **Open question:** Google forces **`videos.insert`** uploads from unverified API projects to private. The docs don't say whether this applies to `liveBroadcasts.insert`. Check on the first real test. If broadcasts are forced private, options are a Google audit, or creating the broadcast in YouTube Studio and only driving the stream.

## What has and hasn't been tested
- Tested in the Linux cloud sandbox: the full dry-run cycle (start → both outputs and the backup receive video → toggle guard → stop → history, with next week cleared). Also: a refused output doesn't trigger restarts, and the phone page renders in light and dark mode. All 5 tests pass.
- **Never run against real YouTube, Facebook or OBS**, and **never run on macOS.** Things to watch on the first real run:
  - Homebrew ffmpeg has RTMPS (TLS), which Facebook needs.
  - `obsws-python` `set_stream_service_settings("rtmp_custom", {...})` works with their OBS version.
  - `open -a OBS` app name.
  - `%d` in `dateFormat` (leading zero is stripped in code).
  - The LaunchAgent PATH finds `/opt/homebrew/bin/ffmpeg`.

## Remaining setup on the Mac (in order)
1. `brew install ffmpeg python`, then `pip3 install obsws-python`.
2. Clone the repo and check out the branch. `cp config.example.json config.json`. Set a random `accessKey` and `obs.password`.
3. OBS: Tools → WebSocket Server Settings → enable it and copy the password. Output (Advanced → Streaming): CBR, 4500–6000 Kbps, **keyframe interval 2 s**, 128 kbps audio. Audio 48 kHz. Advanced → auto-reconnect on, 2 s delay.
4. Run the tests, then a dry run (`"dryRun": true`, `python3 server.py`, open `http://localhost:8080`).
5. YouTube: confirm the channel has live streaming enabled. Create a Google Cloud project, enable YouTube Data API v3, set the consent screen to External and **publish it**, create a Desktop OAuth client, then `python3 setup_youtube.py`. Sign in as the channel owner; this needs a browser on the Mac.
6. Facebook: create a Meta developer app (Page-management use case), then in Graph API Explorer get a User token with `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, selecting the ISNWO Page. Run `python3 setup_facebook.py`.
7. Real test with `youtube.privacy = "unlisted"`. Check both links, end the stream, delete the test videos, set privacy back to `public`.
8. `bash macos/install-autostart.sh`. Set the Mac to log in automatically and restart after a power failure. Give it a fixed IP (DHCP reservation).
9. Remote access: Tailscale on the Mac and the phones. **Never** port-forward 8080.
10. Mimbar button: **Flic 2 + Flic Hub** (Internet Request: click → `/api/start?key=…`, hold → `/api/stop?key=…`). The cheaper alternative is a Bluetooth clicker + Hammerspoon, but only if the mimbar is within about 10 m of the Mac Studio.

## Other context
- The repo also has `obs-scheduled-recording/`, an earlier script that schedules OBS recordings with `obsws-python`.
- A cloud session tried to reach the Mac through Remote Control. The Mac ("Mac.lan", folder "Khutbah Live") was listed but not offered to cloud sessions (reason unknown: folder location, app version or feature availability). That's why the work moved to a local session.
- Pull request: https://github.com/m-siddiqui/General-Code/pull/1 (from this branch; new commits pushed to the branch update it).
- Commit and push only on the branch above. Don't commit `config.json`, `data/` or `recordings/`.
