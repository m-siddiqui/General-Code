# Khutbah Live

One button (on a phone, or a physical button at the mimbar) takes the Jumu'ah khutbah live on
**YouTube and the masjid's Facebook Page at the same time**, with this week's title and description.
Press it again (or tap **End Stream**) and both streams end. The recordings are already on both
platforms, with no trimming and no uploading.

```
IP camera ─► OBS (Mac Studio) ─► local relay (ffmpeg, no re-encoding) ─┬─► YouTube Live
                                                                       ├─► Facebook Page Live
                                                                       └─► backup file in recordings/
        ▲
        └── Khutbah Live server (this folder): creates both live events with the title/description,
            starts/stops OBS, ends the events. Controlled from a phone page or a button.
```

It's free. It uses OBS (which you already have), ffmpeg and Python, and talks to YouTube and Facebook
through their official APIs.

---

## Weekly use

1. **Any time before Friday:** open the control page on your phone, type the **speaker** and **topic**, tap **Save**.
   The page shows the exact title and description that will be used. If nobody fills it in,
   the title is just `Jumu'ah Khutbah | <date>`.
2. **When the khateeb stands up:** press the button at the mimbar (or **Go Live** on the phone).
   Within about 10 seconds both platforms are live.
3. **When the khutbah ends:** hold the button (or tap **End Stream**). Both streams end and stay on
   YouTube and Facebook as videos. Speaker and topic are cleared for next week.

Safety nets:
- **Forgot to stop?** It ends automatically after `maxDurationMinutes` (75 by default).
- **Someone stopped OBS by hand?** The live events are ended automatically.
- **Accidental double-press?** A press within the first minute of going live is ignored by the single-button `toggle` action.
- **One platform has a problem?** The other keeps going. If a platform drops mid-stream, it's retried automatically.
- **The Mac Studio restarted the app mid-khutbah?** It picks the live session back up and OBS reconnects.
- A **backup copy** of every khutbah is saved in `recordings/`.

---

## One-time setup (about an hour)

### 1. Install the tools on the Mac Studio

Open Terminal:

```bash
# Homebrew, if not installed already: https://brew.sh
brew install ffmpeg python
pip3 install obsws-python
```

Copy this `khutbah-live` folder onto the Mac Studio (for example into your home folder), then:

```bash
cd ~/khutbah-live
cp config.example.json config.json
open -e config.json
```

In `config.json`, set:
- `accessKey`: make up a password (letters and numbers, at least 6 characters). Phones and buttons need it.
- `obs.password`: from OBS, see the next step.

### 2. OBS settings

- **Tools → WebSocket Server Settings:** tick *Enable WebSocket server*, click *Show Connect Info*,
  and copy the password into `config.json`.
- **Settings → Output** (Output Mode: *Advanced* → *Streaming* tab):
  Rate control **CBR**, bitrate **4500–6000 Kbps** for 1080p, **Keyframe Interval 2 s**.
  Audio bitrate 128 kbps. Facebook requires the 2-second keyframe interval.
- **Settings → Audio:** sample rate **48 kHz**.
- **Settings → Advanced → Automatically Reconnect:** on, Retry Delay **2 s**.
- You don't need to set a stream key. The app points OBS at the local relay by itself.

### 3. Connect YouTube

1. Make sure live streaming is enabled on the channel: YouTube Studio → **Create → Go live**.
   The first time, this can take up to 24 hours to activate.
2. Go to <https://console.cloud.google.com/>, create a project (e.g. "Khutbah Live").
3. **APIs & Services → Library**: enable **YouTube Data API v3**.
4. **APIs & Services → OAuth consent screen** (also called *Google Auth Platform*):
   User type **External**, fill in the app name and your email, and add yourself as a test user.
   Then go to **Audience** and click **Publish app** so the status is **In production**.
   *This matters:* while the app is in "Testing", Google signs you out after 7 days and the button stops working.
   You don't need Google's verification for your own use.
5. **Credentials → Create credentials → OAuth client ID → Application type: Desktop app.**
   Note the Client ID and Client secret.
6. On the Mac Studio:
   ```bash
   python3 setup_youtube.py
   ```
   Paste the ID and secret, then sign in with the Google account that **owns the masjid's YouTube channel**.
   Google will warn *"Google hasn't verified this app"*. That's expected because it's your own app.
   Click **Advanced → Go to Khutbah Live**.
   (If the account manages several channels, pick the masjid's channel when asked.)

### 4. Connect the Facebook Page

1. Go to <https://developers.facebook.com/apps>, **Create app**. When asked for a use case, choose
   the option for managing a Page (e.g. *"Manage everything on your Page"*). Give it a name like "Khutbah Live".
   You (a Page admin) are the app's admin. The app can stay in development mode because only you use it.
2. Note the **App ID** and **App Secret** (App settings → Basic).
3. Open the **Graph API Explorer**: <https://developers.facebook.com/tools/explorer/>
   - Meta App: your new app. User or Page: **User Token**.
   - Add permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
   - Click **Generate Access Token**, choose the **ISNWO Page** when asked, and copy the token.
4. On the Mac Studio:
   ```bash
   python3 setup_facebook.py
   ```
   Paste the App ID, App Secret and token. It saves a Page token that **does not expire**.
   If you later change your Facebook password or remove the app, run this again.

Secrets are stored in `data/secrets.json`, readable only by your Mac user. Never share that folder.

### 5. Test it

**Dry run (nothing goes to YouTube or Facebook):** set `"dryRun": true` in `config.json`, then:

```bash
python3 server.py
```

Open `http://localhost:8080` on the Mac, enter the access key, press **Go Live**, then **End Stream**.
A test pattern is "streamed" into `data/dryrun/`. Use this to try out the phone and the button.

**Real test:** set `"dryRun": false`, and for the first try set `"youtube": {"privacy": "unlisted"}`.
Open OBS with the camera, go live from the phone, check both links on the page, then end it.
Afterwards, delete the test videos and set privacy back to `"public"`.

### 6. Start automatically with the Mac Studio

```bash
bash macos/install-autostart.sh
```

From now on it starts at login, restarts if it crashes, and keeps the Mac awake.
Also set the Mac to log in automatically (System Settings → Users & Groups) and to restart after a power
failure (System Settings → Energy). OBS is opened automatically when you press Go Live.
Logs are in `data/server.log`.

---

## Using it remotely (from anywhere)

On the masjid Wi-Fi, open `http://<mac-studio-ip>:8080` (the install script prints the address).
On iPhone, use **Share → Add to Home Screen** so it works like an app.

To use it **away from the masjid**, install **Tailscale** (free) on the Mac Studio and on your phone,
signed in to the same account. Then open `http://<mac-studio-name>:8080` from anywhere.
**Don't** forward port 8080 on the router. Tailscale is the safe way to reach it.

---

## A button at the mimbar

The server accepts simple web requests, so almost any smart button works:

| URL (replace `MAC` and `KEY`) | What it does |
|---|---|
| `http://MAC:8080/api/start?key=KEY` | Go live (does nothing if already live) |
| `http://MAC:8080/api/stop?key=KEY` | End (does nothing if not live) |
| `http://MAC:8080/api/toggle?key=KEY` | For one-action buttons: go live, or end if live for more than a minute |

GET and POST both work.

**Recommended: a Flic 2 button with a Flic Hub (Mini or LR).** The button sticks onto the mimbar.
The hub plugs into USB power anywhere within Bluetooth range and joins the masjid Wi-Fi, so it doesn't
rely on a phone or on the Mac being nearby. In the Flic app, add an **Internet Request** action:
- **Click** → `http://MAC:8080/api/start?key=KEY`
- **Hold** → `http://MAC:8080/api/stop?key=KEY`

Using separate click/hold actions means an accidental extra tap can never end the stream.
(Instead of the hub, the Flic app on an old phone or tablet left plugged in at the masjid also works.)

**Cheapest: a Bluetooth presentation clicker paired to the Mac Studio** plus the free
[Hammerspoon](https://www.hammerspoon.org/) app. See `macos/hammerspoon-init.lua`.
This only works if the mimbar is within Bluetooth range of the Mac Studio (about 10 m, less through walls).

**iPhone Shortcuts** can also call these URLs ("Get Contents of URL"), so "Hey Siri, start khutbah" is possible.

Tip: give the Mac Studio a fixed IP address in the router (DHCP reservation) so button URLs keep working.

---

## Settings reference (`config.json`)

| Setting | Meaning |
|---|---|
| `templates.titleParts` | Pieces of the title, joined by `titleSeparator`. A piece whose `{speaker}`/`{topic}` is empty is left out. |
| `templates.descriptionLines` | Lines of the description. A line whose placeholder is empty is left out. Placeholders: `{speaker}`, `{topic}`, `{date}`. |
| `dateFormat` | How `{date}` looks (`%d %B %Y` → 27 November 2026). |
| `maxDurationMinutes` | Auto-end after this long (0 = never). |
| `youtube.privacy` | `public`, `unlisted` or `private`. |
| `youtube.playlistId` | Optional: add each khutbah to this playlist (the ID after `list=` in a playlist URL). |
| `youtube.enabled` / `facebook.enabled` | Turn a platform off without removing its setup. |
| `relay.backupDir` | Folder for backup copies. Remove the setting to turn backups off. |

## Troubleshooting

- **"Could not go live: … YouTube is not connected"**: run `python3 setup_youtube.py`.
- **YouTube stops working after a week**: the Google app is still in "Testing". Publish it (step 3.4) and run `setup_youtube.py` again.
- **"Can't reach OBS"**: OBS's WebSocket server is off, or the password in `config.json` is wrong.
- **Facebook error about permissions**: re-do step 4.3 and make sure all three permissions are ticked and the Page is selected.
- **Live on one platform only**: open *Recent khutbahs & activity log* on the page. The relay logs which platform refused the connection and why.
- Run the automated tests with `python3 -m unittest discover tests -v` (needs ffmpeg).
