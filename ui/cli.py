"""
Command-line interface for RIPTIDAL.

This module provides a command-line interface for the application.
"""

import asyncio
import aiofiles
import json
import shutil
from pathlib import Path # Used in handle_check_track_index
from typing import Dict, List, Optional, Any, Tuple, Set, Union # Keep Union if used elsewhere

from riptidal import __version__
from riptidal.api.auth import AuthManager
from riptidal.api.client import TidalClient
from riptidal.core.downloader import BatchDownloader
from riptidal.core.settings import Settings
from riptidal.core.track_manager import TrackManager
from riptidal.ui.progress_display import RichProgressManager
from riptidal.ui.input_utils import get_input
from riptidal.ui.handlers import AuthHandler, SettingsHandler, DownloadHandler
from riptidal.ui.handlers.library_upgrade_handler import LibraryUpgradeHandler
from riptidal.ui.menu import Menu, MenuItem # Import Menu system
from riptidal.utils.logger import get_logger


class CLI:
    """
    Command-line interface for RIPTIDAL.
    
    This class provides methods for interacting with the user
    through the command line.
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize the CLI.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = get_logger(__name__)
        self.client = TidalClient(settings)
        self.auth_manager = AuthManager(self.client, settings)
        self.track_manager = TrackManager(settings)
        self.progress_manager = RichProgressManager()
        
        self.auth_handler = AuthHandler(self.auth_manager, self.settings, self.progress_manager)
        self.settings_handler = SettingsHandler(self.settings, self.progress_manager, self)
        
        self.batch_downloader = BatchDownloader(
            self.client,
            settings,
            self.progress_manager.update_progress,
            self.track_manager
        )
        self.download_handler = DownloadHandler(
            self.settings,
            self.client,
            self.auth_manager,
            self.track_manager,
            self.batch_downloader,
            self.progress_manager
        )
        
        self.library_upgrade_handler = LibraryUpgradeHandler(
            self.client,
            self.settings,
            self.track_manager,
            self.batch_downloader,
            self.progress_manager
        )

    async def print_logo(self) -> None:
        """Print the application logo."""
        logo = f"""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║                                                                    ║
║                                                                    ║
║       ██████╗ ██╗██████╗ ████████╗██╗██████╗  █████╗ ██╗           ║
║       ██╔══██╗██║██╔══██╗╚══██╔══╝██║██╔══██╗██╔══██╗██║           ║
║       ██████╔╝██║██████╔╝   ██║   ██║██║  ██║███████║██║           ║
║       ██╔══██╗██║██╔═══╝    ██║   ██║██║  ██║██╔══██║██║           ║
║       ██║  ██║██║██║        ██║   ██║██████╔╝██║  ██║███████╗      ║
║       ╚═╝  ╚═╝╚═╝╚═╝        ╚═╝   ╚═╝╚═════╝ ╚═╝  ╚═╝╚══════╝      ║
║                                                                    ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝


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

                        Version {__version__}
"""
        print(logo)
    
    async def handle_login(self) -> bool:
        return await self.auth_handler.handle_login()

    async def handle_logout(self) -> None:
        await self.auth_handler.handle_logout()

    async def handle_api_key_selection(self) -> None:
        await self.settings_handler.handle_api_key_selection()

    async def handle_settings(self) -> None:
        await self.settings_handler.handle_settings()
    
    async def handle_download_favorites(self) -> None:
        await self.download_handler.handle_download_favorites()
    
    async def handle_download_playlist(self) -> None:
        await self.download_handler.handle_download_playlist()
    
    async def handle_resume_albums(self) -> None:
        await self.download_handler.handle_resume_albums()
    
    async def handle_download_favorite_albums(self) -> None:
        await self.download_handler.handle_download_favorite_albums()
    
    async def handle_download_favorite_artists(self) -> None:
        await self.download_handler.handle_download_favorite_artists()
    
    async def handle_download_favorite_videos(self) -> None:
        await self.download_handler.handle_download_favorite_videos()
    
    async def handle_download_favorite_artist_videos(self) -> None:
        await self.download_handler.handle_download_favorite_artist_videos()
        
    async def handle_debug_track_qualities(self) -> None:
        """Debug function to check available qualities for tracks."""
        from riptidal.ui.input_utils import get_input, get_yes_no
        from riptidal.api.models import StreamQuality
        import tabulate
        
        self.progress_manager.stop_display()
        print("\n=== Debug Track Qualities ===")
        
        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to debug track qualities.")
            return
        
        # Ask for track ID or scan favorites
        print("1. Check a specific track ID")
        print("2. Scan favorite tracks")
        print("0. Back")
        
        choice = await get_input("Enter your choice")
        
        if not choice or choice == "0":
            return
        
        if choice == "1":
            track_id = await get_input("Enter track ID")
            if not track_id:
                return
            
            print(f"Probing qualities for track ID: {track_id}")
            try:
                # Get track details first
                track = await self.client.get_track(track_id)
                print(f"Track: {track.title} by {track.artist_names}")
                
                # Probe qualities
                qualities = await self.client.probe_track_qualities(track_id)
                
                # Display results in a table
                print("\nAvailable Qualities:")
                table_data = []
                headers = ["Quality", "Available", "Actual Quality", "Sample Rate", "Bit Depth", "Codec"]
                
                for quality_name, details in qualities.items():
                    if quality_name != "summary":  # Skip summary for the table
                        table_data.append([
                            quality_name,
                            "✓" if details.get("available", False) else "✗",
                            details.get("actual_quality", "N/A"),
                            details.get("sample_rate", "N/A"),
                            details.get("bit_depth", "N/A"),
                            details.get("codec", "N/A")
                        ])
                
                print(tabulate.tabulate(table_data, headers=headers, tablefmt="grid"))
                
                # Display summary
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
                    else:
                        print(f"No qualities available: {summary.get('error', 'Unknown error')}")
                
            except Exception as e:
                print(f"Error probing track qualities: {str(e)}")
        
        elif choice == "2":
            # Scan favorite tracks
            limit = await get_input("Enter number of tracks to scan (default: 10)")
            try:
                limit = int(limit) if limit else 10
            except ValueError:
                limit = 10
            
            print(f"Scanning up to {limit} favorite tracks...")
            
            try:
                # Get favorite tracks
                favorite_tracks = await self.client.get_favorite_tracks()
                if not favorite_tracks:
                    print("No favorite tracks found.")
                    return
                
                # Limit the number of tracks to scan
                tracks_to_scan = favorite_tracks[:limit]
                print(f"Found {len(favorite_tracks)} favorite tracks, scanning {len(tracks_to_scan)}...")
                
                # Prepare results table
                table_data = []
                headers = ["Track", "Artist", "MAX Quality", "Sample Rate", "Bit Depth"]
                
                # Scan each track
                for i, track in enumerate(tracks_to_scan):
                    print(f"Scanning track {i+1}/{len(tracks_to_scan)}: {track.title}")
                    
                    try:
                        # Probe qualities
                        qualities = await self.client.probe_track_qualities(track.id)
                        
                        # Get MAX quality result
                        max_quality = qualities.get("MAX", {})
                        actual_quality = max_quality.get("actual_quality", "N/A")
                        sample_rate = max_quality.get("sample_rate", "N/A")
                        bit_depth = max_quality.get("bit_depth", "N/A")
                        
                        # Add to table
                        table_data.append([
                            track.title,
                            track.artist_names,
                            actual_quality,
                            sample_rate,
                            bit_depth
                        ])
                        
                    except Exception as e:
                        print(f"Error probing track {track.id}: {str(e)}")
                        table_data.append([
                            track.title,
                            track.artist_names,
                            "ERROR",
                            "N/A",
                            "N/A"
                        ])
                
                # Display results
                print("\nQuality Scan Results:")
                print(tabulate.tabulate(table_data, headers=headers, tablefmt="grid"))
                
                # Summarize results
                quality_counts = {}
                for row in table_data:
                    quality = row[2]
                    if quality not in quality_counts:
                        quality_counts[quality] = 0
                    quality_counts[quality] += 1
                
                print("\nQuality Distribution:")
                for quality, count in quality_counts.items():
                    percentage = (count / len(table_data)) * 100
                    print(f"{quality}: {count} tracks ({percentage:.1f}%)")
                
            except Exception as e:
                print(f"Error scanning favorite tracks: {str(e)}")
        
        else:
            print("Invalid choice.")
    
    async def handle_check_track_index(self) -> None:
        """Diagnostic function to check and repair the track index."""
        from riptidal.ui.input_utils import get_yes_no
        
        self.progress_manager.stop_display()
        print("\n=== Check Track Index ===")
        
        # Check if index file exists
        if self.track_manager.index_path.exists():
            file_size = self.track_manager.index_path.stat().st_size
            print(f"Track index file exists at: {self.track_manager.index_path}")
            print(f"File size: {file_size} bytes")
            
            # Check if it's readable
            try:
                async with aiofiles.open(self.track_manager.index_path, "r", encoding="utf-8") as f:
                    data = await f.read()
                
                # Check if it's valid JSON
                try:
                    index_data = json.loads(data)
                    track_count = len(index_data)
                    print(f"Track index contains {track_count} tracks")
                    print("Track index file is valid")
                except json.JSONDecodeError:
                    print("Track index file contains invalid JSON")
                    if await get_yes_no("Attempt to repair?", True):
                        # Create a backup
                        backup_path = self.track_manager.index_path.with_suffix(".json.bak")
                        shutil.copy(self.track_manager.index_path, backup_path)
                        print(f"Created backup at: {backup_path}")
                        
                        # Create a new empty index
                        await self.track_manager.save_index()
                        print("Created new empty track index")
            except Exception as e:
                print(f"Error reading track index: {str(e)}")
        else:
            print(f"Track index file does not exist at: {self.track_manager.index_path}")
            
            # Check directory
            parent_dir = self.track_manager.index_path.parent
            if parent_dir.exists():
                print(f"Parent directory exists: {parent_dir}")
                
                # Check if directory is writable
                try:
                    test_file = parent_dir / ".write_test"
                    with open(test_file, "w") as f:
                        f.write("test")
                    test_file.unlink()
                    print("Directory is writable")
                except Exception as e:
                    print(f"Directory is not writable: {str(e)}")
            else:
                print(f"Parent directory does not exist: {parent_dir}")
            
            if await get_yes_no("Create new track index?", True):
                try:
                    # Ensure directory exists
                    parent_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Create empty index
                    await self.track_manager.save_index()
                    
                    if self.track_manager.index_path.exists():
                        print(f"Successfully created track index at: {self.track_manager.index_path}")
                    else:
                        print("Failed to create track index")
                except Exception as e:
                    print(f"Error creating track index: {str(e)}")
        
        # Scan download directory for tracks
        if await get_yes_no("Scan download directory for tracks?", False):
            print(f"Scanning download directory: {self.settings.download_path}")
            await self.track_manager.scan_directory(self.settings.download_path)
            print(f"Found {len(self.track_manager.local_tracks)} tracks")
            await self.track_manager.save_index()
            print("Updated track index")

    async def handle_clear_library_index(self) -> None:
        """Administrative function to clear all library indexes (unified + legacy)."""
        from riptidal.ui.input_utils import get_yes_no

        self.progress_manager.stop_display()
        print("\n=== Clear Library Index ===")
        print("This will clear the unified library_state.json and legacy .data indexes.")
        print("No media files on disk will be deleted.")

        try:
            counts = await self.track_manager.get_index_counts()
        except Exception as e:
            counts = {"tracks": 0, "albums": 0, "videos": 0}
            self.logger.warning(f"Could not read current index counts: {e}")

        print(f"Current counts -> Tracks: {counts.get('tracks', 0)}, Albums: {counts.get('albums', 0)}, Videos: {counts.get('videos', 0)}")

        if not await get_yes_no("Proceed to clear all index data? (Backups will be created)", False):
            print("Operation cancelled.")
            return
        if not await get_yes_no("Are you absolutely sure? This cannot be undone.", False):
            print("Operation cancelled.")
            return

        try:
            prev = await self.track_manager.clear_all_indexes(backup=True)
            print("\nIndexes cleared.")
            print(f"Previous counts -> Tracks: {prev.get('tracks', 0)}, Albums: {prev.get('albums', 0)}, Videos: {prev.get('videos', 0)}")
            now = await self.track_manager.get_index_counts()
            print(f"Current counts  -> Tracks: {now.get('tracks', 0)}, Albums: {now.get('albums', 0)}, Videos: {now.get('videos', 0)}")
            print("Backups were saved next to the original files with .bak.TIMESTAMP suffixes.")
        except Exception as e:
            self.logger.error(f"Error clearing library indexes: {e}", exc_info=True)
            print(f"Error clearing library indexes: {e}")

    async def handle_backfill_downloaded_at(self) -> None:
        from riptidal.ui.input_utils import get_yes_no
        self.progress_manager.stop_display()
        print("\n=== Backfill Downloaded Timestamps ===")
        print("This will populate 'downloaded_at' for tracks in the library index that have it missing,")
        print("using the file's last modification time when available, or current time otherwise.")
        print("No media files will be changed.")
        if not await get_yes_no("Proceed?", True):
            print("Operation cancelled.")
            return
        try:
            summary = await self.track_manager.backfill_downloaded_at()
            print(
                f"Backfill complete. Total: {summary.get('total',0)}, "
                f"Updated from file mtime: {summary.get('updated',0)}, "
                f"Already set: {summary.get('already_set',0)}, "
                f"Used current time: {summary.get('used_current_time',0)}"
            )
        except Exception as e:
            self.logger.error(f"Backfill error: {e}", exc_info=True)
            print(f"Error during backfill: {e}")
            
    async def handle_backfill_metadata(self) -> None:
        from riptidal.ui.input_utils import get_yes_no, get_input
        self.progress_manager.stop_display()
        print("\n=== Backfill Library Metadata ===")
        print("This will populate missing artist/album metadata for tracks in the library index")
        print("by querying the Tidal API. This may take some time depending on your library size.")
        
        if not await self.auth_manager.ensure_logged_in():
            print("You need to be logged in to backfill metadata from Tidal.")
            return
            
        reconcile_favorites = await get_yes_no("Also mark tracks that are in your Favorites?", True)
        
        limit_str = await get_input("Maximum tracks to process (leave empty for all)")
        max_items = None
        if limit_str:
            try:
                max_items = int(limit_str)
                if max_items <= 0:
                    print("Invalid limit. Processing all tracks.")
                    max_items = None
                else:
                    print(f"Will process up to {max_items} tracks.")
            except ValueError:
                print("Invalid limit. Processing all tracks.")
        
        if not await get_yes_no("Proceed with metadata backfill?", True):
            print("Operation cancelled.")
            return
            
        try:
            print("Starting metadata backfill...")
            summary = await self.track_manager.backfill_metadata(
                self.client,
                reconcile_favorites=reconcile_favorites,
                rate_limit_seconds=0.2,  # 5 requests per second max
                max_items=max_items
            )
            
            print("\n=== Metadata Backfill Complete ===")
            print(f"Tracks processed: {summary.get('total_candidates',0)}")
            print(f"Updated: {summary.get('updated',0)}")
            print(f"Skipped: {summary.get('skipped',0)}")
            print(f"Errors: {summary.get('errors',0)}")
            if reconcile_favorites:
                print(f"Favorites reconciled: {summary.get('reconciled_favorites',0)}")
                
        except Exception as e:
            self.logger.error(f"Metadata backfill error: {e}", exc_info=True)
            print(f"Error during metadata backfill: {e}")

    async def _build_main_menu(self) -> Menu:
        """Builds the main menu object."""
        items = [
            MenuItem(label="Download Favorite Tracks", action=self.handle_download_favorites),
            MenuItem(label="Download Favorite Albums", action=self.handle_download_favorite_albums),
            MenuItem(label="Download Favorite Artists", action=self.handle_download_favorite_artists),
            MenuItem(label="Download Favorite Videos", action=self.handle_download_favorite_videos),
            MenuItem(label="Download Favorite Artist Videos", action=self.handle_download_favorite_artist_videos),
            MenuItem(label="Download Playlist", action=self.handle_download_playlist),
            MenuItem(label="Settings", action=self.handle_settings),
            MenuItem(label="Login", action=self.handle_login),
            MenuItem(label="Logout", action=self.handle_logout),
        ]
        return Menu(title="Main Menu", items=items)

    async def start(self) -> int:
        """
        Start the CLI.
        """
        await self.print_logo()
        
        if self.auth_manager.is_logged_in():
            print(f"Logged in as user {self.settings.user_id}")
        else:
            print("Not logged in")
        
        main_menu = await self._build_main_menu()
        exit_code = 0
        
        try:
            while True:
                self.progress_manager.stop_display()
                self.progress_manager.reset_progress_state()

                action_result = await main_menu.display()
                
                if action_result is None:
                    print("Goodbye!")
                    break
                                
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            exit_code = 1
        except Exception as e:
            self.logger.error(f"CLI Error: {e}", exc_info=True)
            print(f"\nAn unexpected error occurred: {e}")
            exit_code = 1
        finally:
            self.progress_manager.stop_display()
            await self.client.close()
            
        return exit_code
