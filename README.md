# GTA V Self Radio Spotify Relay

Sync Spotify playlists into GTA V Self Radio by downloading audio tracks to your GTA V User Music folder.

## Features

- Sync any Spotify playlist to GTA V Self Radio
- Sync Liked Songs
- Interactive playlist picker in terminal
- Incremental sync (skips already downloaded tracks)
- Watch mode for automatic re-sync
- ID3 metadata tagging
- Parallel downloads
- Optional cleanup of removed tracks

## Prerequisites

1. Python 3.10+
2. FFmpeg
   ```powershell
   winget install Gyan.FFmpeg
   ```
3. Spotify Developer account

## Installation

```powershell
git clone https://github.com/HarshitKumar9030/gta-v-self-radio.git
cd gta-v-self-radio

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -e .
```

## Configuration

1. Create an app at Spotify Developer Dashboard.
2. Add this Redirect URI in app settings:
   ```
   https://127.0.0.1:8888/callback
   ```
3. Copy `.env.example` to `.env` and fill credentials:

```ini
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=https://127.0.0.1:8888/callback
```

## Authentication Flow

Run:

```powershell
gta-radio auth
```

The browser will open Spotify login and then redirect to `https://127.0.0.1:8888/callback?...`.
If the page cannot load, copy the full URL from the browser address bar and paste it into the terminal when prompted.

## Usage

```powershell
gta-radio setup
gta-radio playlists
gta-radio sync -i
gta-radio sync -p "<playlist_id_or_url>"
gta-radio sync --liked -n 100
gta-radio watch -i
gta-radio status
```

## GTA V Self Radio

After syncing tracks:

1. Open GTA V -> Settings -> Audio
2. Set Self Radio mode (Sequential or Radio)
3. Run Quick Scan or Full Scan
4. Tune to Self Radio in-game

## Configuration Options

| Variable | Default | Description |
|---|---|---|
| `SPOTIFY_CLIENT_ID` | — | Spotify app Client ID |
| `SPOTIFY_CLIENT_SECRET` | — | Spotify app Client Secret |
| `SPOTIFY_REDIRECT_URI` | `https://127.0.0.1:8888/callback` | OAuth redirect URI |
| `GTA_MUSIC_DIR` | Auto-detected | GTA V User Music folder |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Parallel download workers |
| `AUDIO_BITRATE` | `320` | MP3 bitrate (kbps) |
| `AUDIO_FORMAT` | `mp3` | Output format |
| `WATCH_INTERVAL_SECONDS` | `300` | Watch mode interval |

## Disclaimer

Use this tool only for content you have rights to access and use.

## License

MIT
