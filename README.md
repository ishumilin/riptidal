# RIPTIDAL

```
..............................................................................................................
..............................................................................................................
..................................................@@. @@@@@@@ ................................................
................................................@@@@@@@#@*@@-@@...............................................
................................................%@@  *@@@@@@%@=@..............................................
..............................................@*@@*@#-@##:-@@@%@@: ...........................................
...........................................@-@@@@%@@@%##@@@@@@@%@@ ...........................................
.........................................@%=@@#####@@@%%@@#%@@@@#@+ ..........................................
.........................................@@@%%@@@@*%@@@@###%@@@@@@@.@ ........................................
........................................ @@@@@@=+- .@+%@@@@@@@@@@%#@#@@%+@@ @..#  ............................
......................................... @.= .....@%%@@@@@ @@@@@@%#@*@+@@*@*@%%@@@  .........................
.........................................  .......#@@@@@. ... @@@@@@%%%**@*@*@*=@=@#@@. ......................
.....................................#@@@@+**%.. .@.@@@ .......@@@@@%%%@%%@%@%%@%%*@-*%@#@....................
....................................@@@@@@++*@@. @@@@.........@@@@@-#%@@%%@%@%@%%@%#@@@@@:  ..................
...................................@@@@@=:=@@@@@  ............@@@@*#@@@@@@@@@@@@@@@@@@@@%@@  .................
...................................@@@@:=.-:@@@@ .............@@@@@%@@@@@@@@@@@@@#++@@%%@@@@@ ................
...................................@@@@+@@@@@@@@..............@@ @@#@@@@@@@@@@@@*=*%@%@%@@@@@@................
....................................@*+*+@@@@@@...........@@@@.  -%%@@@@@@@@@@@%=@@%%@%@@@@@@@  ..............
.......................................@*@@@.............@@  .@@@=  @@@@@@@@@@#=@@%%@@@@@@@@@@@ ..............
........................................................-@@  %@# ...@@@@@@@@@#-#@@@@@@@@@@@@@@@@@.............
.........................................................#   @@  ..@@@@@@@@@%=*%@@@@@@@@@@@@@@%@@@ ...........
............................................................. *  .@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@*@@ .........
................................................................. @@@@@@@  @@@@@@@@@@@@@@@@@@@@@@@#%@=:.......
...................................................................+@@@@@@. @@@@@@@. ...@@@@@@@@@@@@%@%@......
.....................................................................@@@@@@  .@@@@@@ ..... .@@@@@@@@@@@+@ ....
...................................................................... .@@@@% ..@@@@+ ..........@@@@@@@@+@:...
....................................................................... .@@@@ ....@@@@............ @@@@@%%@:..
...................................................................... .@@@......@@@@..............  @@@@@@@..
......................................................................@@@@. ....:@@@ ...............-@@@@@@:..
....................................................................@@@@@#     @@@@@  ....... = .@@@=@@@@@@...
.............................................................@@@@@@@@@@@@*@#%@@@+@@@@@@@*@%%@@@@@@@@@@@@@.....
```

A modern, Python 3.12+ application for downloading music from Tidal.

---

## 🚨 CRITICAL LEGAL WARNING

**READ THIS CAREFULLY BEFORE USING THIS SOFTWARE**

**USE AT YOUR OWN RISK - SERIOUS CONSEQUENCES MAY APPLY**

### Important Notice About Terms of Service

- This tool interacts with Tidal's services in ways that may not align with their intended use
- Tidal's Terms of Service grant users a **revocable license** to access content through their official applications
- **Your Tidal account may be suspended or terminated** at Tidal's discretion
- Tidal states: *"The TIDAL Service and TIDAL Content are licensed, not sold, to you"*
- **You are responsible for ensuring your use complies with Tidal's Terms of Service**

### Potential Legal Risks

**Account & Service Risks:**
- ⚠️ **Account Termination**: Your Tidal account may be suspended or terminated
- ⚠️ **Loss of Subscription**: Potential loss of access without refund
- ⚠️ **Service Restrictions**: Tidal may restrict or limit your access

**Legal Liability Risks:**
- ⚠️ **Copyright Concerns**: Unauthorized copying may have legal implications
- ⚠️ **Terms of Service**: Users must comply with all applicable terms and conditions
- ⚠️ **Local Laws**: You are responsible for compliance with all applicable laws

### No Liability & Disclaimer

**THE AUTHORS AND CONTRIBUTORS DISCLAIM ALL LIABILITY** for:
- Any consequences resulting from use of this software
- Account suspensions, terminations, or restrictions
- Loss of access to paid services or subscriptions
- Any legal consequences or claims
- Any damages, direct or indirect, of any kind
- Compliance with third-party terms of service

**YOU USE THIS SOFTWARE ENTIRELY AT YOUR OWN RISK.**

### Educational Purpose

This project was created for **educational and research purposes** to demonstrate:
- OAuth2 authentication implementation
- Asynchronous Python programming patterns
- API integration techniques
- Audio file handling and metadata management

### Recommended Best Practices

**For legitimate offline listening, we recommend:**
- Using Tidal's official applications for offline downloads
- Maintaining compliance with Tidal's Terms of Service
- Supporting artists through proper licensing channels
- Reviewing and understanding all applicable terms before use

### User Acknowledgment

**BY USING THIS SOFTWARE, YOU ACKNOWLEDGE AND AGREE THAT:**

1. ✓ You have read and understood all warnings in this document
2. ✓ You accept full responsibility for any consequences of use
3. ✓ You will not hold the authors liable for any damages or losses
4. ✓ You are responsible for compliance with all applicable terms and laws
5. ✓ You understand the risks including potential account termination
6. ✓ You will use this software responsibly and legally
7. ✓ You have an active, paid Tidal subscription

**IF YOU DO NOT ACCEPT THESE TERMS AND RISKS, DO NOT USE THIS SOFTWARE.**

---

*(Last minor update: 2025-09-22)*

## Features

- Asynchronous API client for efficient communication with Tidal
- OAuth2 device code flow authentication for secure login
- Download tracks in various qualities (up to MASTER)
- Download videos in various resolutions (up to 1080p)
- Automatic fetching of updated API keys from GitHub
- Track management with duplicate detection
- Full album downloading for favorite tracks
- Album download resumption for interrupted downloads
- Accurate progress tracking for album downloads
- Proper distinction between original favorite tracks and album tracks
- Robust progress tracking for playlist downloads with full albums
- Preserves original track order from Tidal API during downloads
- Downloads tracks in playlist order, downloading each track's album before moving to the next track
- Automatically resumes incomplete album downloads that were interrupted
- Prioritizes incomplete albums by processing them first before starting regular downloads
- Ensures consistent artist folder names for albums by using album artist caching
- Download favorite albums directly from the main menu
- Download all albums from favorite artists with option to include EPs and singles
- Portable application design - all settings and data stored in the project directory

## Requirements

- Python 3.12 or higher
- A Tidal account (free or premium)
- ffmpeg (required for video downloads)

## Installation

### From PyPI

```bash
pip install riptidal
```

### From Source

```bash
git clone https://github.com/ishumilin/riptidal.git
cd riptidal
pip install -e .
```

### Run Without Installation

If you don't want to install the package, you can run it directly from the repository root:

```bash
# From the repository root
python run.py
```

## Usage

### Command Line Interface

If you installed the package:

```bash
riptidal
```

If you're using the run script:

```bash
python run.py
```

This will start the interactive command-line interface, which will guide you through the process of logging in and downloading your favorite tracks.

### Python API

```python
import asyncio
from riptidal.core.settings import Settings, load_settings
from riptidal.api.client import TidalClient
from riptidal.api.auth import AuthManager
from riptidal.core.downloader import BatchDownloader

async def main():
    # Load settings
    settings = load_settings()
    
    # Create client and auth manager
    client = TidalClient(settings)
    auth_manager = AuthManager(client, settings)
    
    # Login
    if not await auth_manager.ensure_logged_in():
        print("Login failed")
        return
    
    # Get favorite tracks
    tracks = await client.get_favorite_tracks()
    print(f"Found {len(tracks)} favorite tracks")
    
    # Download tracks
    downloader = BatchDownloader(client, settings)
    results = await downloader.download_tracks(tracks)
    
    # Print summary
    success = sum(1 for r in results if r.success and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if not r.success)
    
    print(f"Downloaded: {success}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Using the Track Quality Probe API

```python
import asyncio
import json
from riptidal.core.settings import load_settings
from riptidal.api.client import TidalClient
from riptidal.api.auth import AuthManager
from riptidal.api.models import StreamQuality

async def probe_track_quality(track_id):
    # Load settings and create client
    settings = load_settings()
    client = TidalClient(settings)
    auth_manager = AuthManager(client, settings)
    
    # Ensure logged in
    if not await auth_manager.ensure_logged_in():
        print("Login failed")
        return
    
    # Get track details
    track = await client.get_track(track_id)
    print(f"Track: {track.title} by {track.artist_names}")
    
    # Probe available qualities
    qualities = await client.probe_track_qualities(track_id)
    
    # Print results
    print("\nAvailable Qualities:")
    for quality_name, details in qualities.items():
        if quality_name != "summary":
            available = "✓" if details.get("available", False) else "✗"
            print(f"{quality_name}: {available}")
            if details.get("available", False):
                print(f"  - Actual quality: {details.get('actual_quality', 'N/A')}")
                print(f"  - Sample rate: {details.get('sample_rate', 'N/A')}")
                print(f"  - Bit depth: {details.get('bit_depth', 'N/A')}")
                print(f"  - Codec: {details.get('codec', 'N/A')}")
    
    # Print summary
    if "summary" in qualities:
        summary = qualities["summary"]
        print("\nSummary:")
        highest = summary.get("highest_available_quality")
        if highest:
            highest_details = summary.get("highest_quality_details", {})
            print(f"Highest available quality: {highest}")
            print(f"Description: {highest_details.get('description', 'Unknown')}")
            print(f"Sample rate: {highest_details.get('sample_rate', 'Unknown')}")
            print(f"Bit depth: {highest_details.get('bit_depth', 'Unknown')}")

if __name__ == "__main__":
    # Replace with an actual track ID
    asyncio.run(probe_track_quality("12345678"))
```

## Configuration

The application stores its configuration in a portable manner, keeping all files within the project directory:

- Configuration: `.config/settings.json`
- Data: `.data/`
- Cache: `.cache/`
- Downloads: `Downloads/`

This makes the application fully portable - you can copy the entire folder to a USB drive or another computer, and it will work without any additional setup. You can edit the settings file directly, or use the settings menu in the application.

## Project Structure

The project is organized into several packages:

- `api`: Handles communication with the Tidal API
  - `client.py`: Main API client for interacting with Tidal
  - `auth.py`: Authentication manager for OAuth2 device code flow
  - `models.py`: Pydantic models for API responses
  - `keys.py`: API key management with automatic updates from GitHub
- `core`: Contains core functionality like settings, downloading, and track management
  - `settings.py`: Settings management with Pydantic
  - `downloader.py`: Asynchronous download functionality
  - `track_manager.py`: Track management and duplicate detection
  - `album_handler.py`: Handles album-specific fetching and metadata preparation
  - `download_models.py`: Models for download progress, results, and album status
- `ui`: Provides user interface components
  - `cli.py`: Main CLI coordinator
  - `menu.py`: Generic `Menu` and `MenuItem` classes for interactive menus
  - `progress_display.py`: Manages Rich-based progress bar displays
  - `input_utils.py`: Utility functions for common user input prompts
  - `handlers/`: Directory for specific action handler classes
    - `auth_handler.py`: Handles login and logout
    - `settings_handler.py`: Manages application settings and API key selection
    - `download_handler.py`: Orchestrates track/playlist downloads and M3U creation
- `utils`: Contains utility functions for logging and path management
  - `logger.py`: Logging setup and utilities
  - `paths.py`: Path management and file operations
- `tests`: Comprehensive test suite for all components

## Development

### Setup Development Environment

```bash
git clone https://github.com/ishumilin/riptidal.git
cd riptidal
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest
```

### Code Formatting

```bash
black .
isort .
```

### Type Checking

```bash
mypy riptidal
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- Based on the original [Tidal-Media-Downloader](https://github.com/yaronzz/Tidal-Media-Downloader) by Yaronzz
- Thanks to the Tidal team for their great music streaming service
