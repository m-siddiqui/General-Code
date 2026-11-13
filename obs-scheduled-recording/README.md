# OBS scheduled recording (macOS)

Starts an OBS Studio recording at a given time, and can stop it at a set time or after a set duration.

## Setup

1. **OBS 28 or newer** (it has the WebSocket server built in).
2. In OBS go to **Tools → WebSocket Server Settings**, tick **Enable WebSocket server**,
   note the port (default `4455`), and click **Show Connect Info** to copy the password.
3. Install the dependency:
   ```bash
   pip3 install obsws-python
   ```

## Usage

```bash
export OBS_WS_PASSWORD='your-password'

# Start at 14:30 today (or tomorrow if that time has passed)
python3 obs_schedule_record.py --start 14:30

# Start at a specific date/time, record for 45 minutes
python3 obs_schedule_record.py --start "2026-11-14 09:00" --duration 45

# Start at 20:00, stop at 21:15, opening OBS automatically if it's closed
python3 obs_schedule_record.py --start 20:00 --stop 21:15 --launch-obs
```

Leave the terminal open until it finishes. To keep your Mac from sleeping while it waits,
run it under `caffeinate`:

```bash
caffeinate -i python3 obs_schedule_record.py --start 14:30 --duration 60
```
