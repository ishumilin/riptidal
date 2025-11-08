"""
Handles authentication-related actions for the CLI.
"""
from typing import TYPE_CHECKING

from riptidal.api.auth import AuthManager
from riptidal.core.settings import Settings, save_settings
from riptidal.ui.input_utils import get_input, get_yes_no

class AuthHandler:
    def __init__(self, auth_manager: AuthManager, settings: Settings, progress_manager: 'RichProgressManager'):
        self.auth_manager = auth_manager
        self.settings = settings
        self.progress_manager = progress_manager

    async def handle_login(self) -> bool:
        """
        Handle the login process.
        
        Returns:
            True if login was successful, False otherwise
        """
        self.progress_manager.stop_display() # Ensure any existing progress display is stopped
        print("\n=== Login ===")
        
        if self.auth_manager.is_logged_in():
            print("You are already logged in.")
            logout_first = await get_yes_no("Do you want to logout and login again?", False)
            if not logout_first:
                return True # Considered successful as already logged in and user chose not to re-login
            # If they choose to logout and login again, proceed with logout then login
            await self.handle_logout(confirm_prompt=False) # Logout without extra confirmation

        print("1. Login with device code")
        print("2. Login with access token")
        print("0. Back")
        
        choice = await get_input("Enter your choice")
        if not choice or choice == "0":
            return False # User chose to go back
        
        login_successful = False
        if choice == "1":
            login_successful = await self.auth_manager.login_with_device_code()
        elif choice == "2":
            token = await get_input("Enter your access token")
            if token: # Only attempt login if token is provided
                login_successful = await self.auth_manager.login_with_token(token)
            else:
                print("No access token entered.")
                return False # No token provided, so login not attempted/failed
        else:
            print("Invalid choice")
            return False # Invalid choice means login failed for this attempt

        if login_successful:
            print(f"Successfully logged in as user {self.settings.user_id}.")
        # Error messages for failed login are handled by AuthManager methods
        return login_successful

    async def handle_logout(self, confirm_prompt: bool = True) -> None:
        """
        Handle the logout process.
        
        Args:
            confirm_prompt: Whether to ask for confirmation before logging out.
        """
        self.progress_manager.stop_display() # Ensure any existing progress display is stopped
        print("\n=== Logout ===")
        
        if not self.auth_manager.is_logged_in():
            print("You are not logged in.")
            return
        
        if confirm_prompt:
            confirm = await get_yes_no("Are you sure you want to logout?", False)
            if not confirm:
                return
        
        # Clear tokens and user info from settings
        self.settings.auth_token = None
        self.settings.refresh_token = None
        self.settings.token_expiry = None
        self.settings.user_id = None
        self.settings.country_code = None
        
        save_settings(self.settings)
        self.auth_manager.client.clear_session_payload()

        print("Logged out successfully.")
