"""
Handles settings-related actions for the CLI.
"""
from typing import TYPE_CHECKING, Any # Import Any
from pathlib import Path

from riptidal.core.settings import Settings, AudioQuality, VideoQuality, save_settings
from riptidal.ui.input_utils import get_input, get_choice, get_yes_no
from riptidal.api.client import TidalClient # Needed for re-init
from riptidal.api.auth import AuthManager # Needed for re-init
from riptidal.core.downloader import BatchDownloader # Needed for re-init


class SettingsHandler:
    def __init__(self, settings: Settings, progress_manager: 'RichProgressManager', cli_instance: Any):
        """
        Initialize the SettingsHandler.
        Args:
            settings: The application settings object.
            progress_manager: The RichProgressManager instance.
            cli_instance: The main CLI instance to update its client, auth_manager, batch_downloader.
        """
        self.settings = settings
        self.progress_manager = progress_manager
        self.cli_instance = cli_instance # To re-initialize client, auth, downloader on API key change

    async def _print_settings_menu(self) -> None:
        """Prints the settings menu."""
        print("\n=== Settings ===")
        print(f"1. Download Path: {self.settings.download_path}")
        print(f"2. Audio Quality: {self.settings.audio_quality.name if hasattr(self.settings.audio_quality, 'name') else self.settings.audio_quality}")
        print(f"3. Video Quality: {self.settings.video_quality.name if hasattr(self.settings.video_quality, 'name') else self.settings.video_quality}")
        print(f"4. Quality Fallback: {'Enabled' if self.settings.quality_fallback else 'Disabled'}")
        print(f"5. Enable Playlists: {'Enabled' if self.settings.enable_playlists else 'Disabled'}")
        print(f"6. Download Full Albums: {'Enabled' if self.settings.download_full_albums else 'Disabled'}")
        print(f"7. Create M3U Playlists: {'Enabled' if self.settings.create_m3u_playlists else 'Disabled'}")
        # Max Concurrent Downloads is now hardcoded to 1
        print(f"8. API Key Selection")
        print("0. Back")
        print("================\n")

    async def handle_api_key_selection(self) -> None:
        """Handle API key selection."""
        from riptidal.api.keys import get_all_keys, get_key # is_key_valid removed as not used

        self.progress_manager.stop_display()
        print("\n=== API Key Selection ===")
        
        keys = get_all_keys()
        current_key_details = get_key(self.settings.api_key_index)
        print(f"Current API key: {current_key_details['platform']} - {current_key_details['formats']}")
        if current_key_details['valid'] != 'True':
            print("WARNING: Current key is marked as invalid. This may cause issues.")
        
        print("\nAvailable API keys:")
        for i, key_info in enumerate(keys):
            valid_str = "Valid" if key_info['valid'] == 'True' else "Invalid"
            current_str = " (Current)" if i == self.settings.api_key_index else ""
            print(f"{i}. {key_info['platform']} - {key_info['formats']} - {valid_str}{current_str}")
        
        choice_str = await get_input("Enter API key index (or press Enter to cancel)")
        if not choice_str:
            return
        
        try:
            index = int(choice_str)
            if 0 <= index < len(keys):
                self.settings.api_key_index = index
                
                # Reinitialize client, auth_manager, and batch_downloader on the CLI instance
                self.cli_instance.client = TidalClient(self.settings)
                self.cli_instance.auth_manager = AuthManager(self.cli_instance.client, self.settings)
                # Ensure the progress_manager's callback and track_manager are correctly passed
                self.cli_instance.batch_downloader = BatchDownloader(
                    self.cli_instance.client, 
                    self.settings, 
                    self.cli_instance.progress_manager.update_progress,
                    self.cli_instance.track_manager  # Pass track_manager to BatchDownloader
                )
                
                selected_key_details = get_key(index)
                print(f"API key changed to: {selected_key_details['platform']} - {selected_key_details['formats']}")
                if selected_key_details['valid'] != 'True':
                    print("WARNING: Selected key is marked as invalid. This may cause issues.")
                save_settings(self.settings) # Save settings immediately
            else:
                print(f"Please enter a number between 0 and {len(keys) - 1}")
        except ValueError:
            print("Please enter a valid number.")

    async def handle_settings(self) -> bool: # Modified return type hint
        """Handle the settings menu."""
        self.progress_manager.stop_display()
        while True:
            await self._print_settings_menu()
            choice = await get_input("Enter your choice")
            
            if not choice or choice == "0":
                save_settings(self.settings)
                print("Settings saved.")
                return True # Return True to signify sub-menu exit, not app exit
            
            if choice == "1":
                path_str = await get_input("Enter download path", str(self.settings.download_path))
                if path_str:
                    try:
                        self.settings.download_path = Path(path_str)
                        self.settings.download_path.mkdir(parents=True, exist_ok=True)
                        print(f"Download path set to: {self.settings.download_path}")
                        save_settings(self.settings) # Save settings immediately
                    except Exception as e:
                        print(f"Error setting download path: {e}")
            elif choice == "2":
                print("Available audio qualities:")
                qualities = list(AudioQuality)
                for i, quality in enumerate(qualities):
                    print(f"{i}. {quality.name}")
                
                quality_idx = await get_choice("Enter audio quality number", qualities, display_choices=False)
                if quality_idx != -1 and 0 <= quality_idx < len(qualities):
                    self.settings.audio_quality = qualities[quality_idx]
                    print(f"Audio quality set to: {self.settings.audio_quality.name}")
                    save_settings(self.settings) # Save settings immediately
            elif choice == "3":
                print("Available video qualities:")
                qualities = list(VideoQuality)
                for i, quality in enumerate(qualities):
                    print(f"{i}. {quality.name}")
                
                quality_idx = await get_choice("Enter video quality number", qualities, display_choices=False)
                if quality_idx != -1 and 0 <= quality_idx < len(qualities):
                    self.settings.video_quality = qualities[quality_idx]
                    print(f"Video quality set to: {self.settings.video_quality.name}")
                    save_settings(self.settings) # Save settings immediately
            elif choice == "4":
                self.settings.quality_fallback = await get_yes_no(
                    "Enable quality fallback?", self.settings.quality_fallback
                )
                print(f"Quality fallback: {'Enabled' if self.settings.quality_fallback else 'Disabled'}")
                save_settings(self.settings) # Save settings immediately
            elif choice == "5":
                self.settings.enable_playlists = await get_yes_no(
                    "Enable playlists?", self.settings.enable_playlists
                )
                print(f"Playlists: {'Enabled' if self.settings.enable_playlists else 'Disabled'}")
                save_settings(self.settings) # Save settings immediately
            elif choice == "6":
                self.settings.download_full_albums = await get_yes_no(
                    "Download full albums for favorite/playlist tracks?", self.settings.download_full_albums
                )
                print(f"Download full albums: {'Enabled' if self.settings.download_full_albums else 'Disabled'}")
                save_settings(self.settings) # Save settings immediately
            elif choice == "7":
                self.settings.create_m3u_playlists = await get_yes_no(
                    "Create M3U playlists?", self.settings.create_m3u_playlists
                )
                print(f"Create M3U playlists: {'Enabled' if self.settings.create_m3u_playlists else 'Disabled'}")
                save_settings(self.settings) # Save settings immediately
            # Option 8 is now API Key Selection
            elif choice == "8":
                await self.handle_api_key_selection() # handle_api_key_selection now saves settings
            else:
                print("Invalid choice.")
