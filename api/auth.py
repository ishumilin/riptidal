"""
Authentication utilities for RIPTIDAL.

This module provides functions for handling authentication with the Tidal API.
"""

import asyncio
import logging
import time
from typing import Optional, Tuple, Dict, Any

from riptidal.api.client import TidalClient, AuthenticationError
from riptidal.core.settings import Settings, save_settings
from riptidal.utils.logger import get_logger


class AuthManager:
    """
    Manager for handling authentication with the Tidal API.
    
    This class provides methods for logging in, refreshing tokens,
    and managing authentication state.
    """
    
    def __init__(self, client: TidalClient, settings: Settings):
        """
        Initialize the authentication manager.
        
        Args:
            client: Tidal API client
            settings: Application settings
        """
        self.client = client
        self.settings = settings
        self.logger = get_logger(__name__)
    
    async def login_with_device_code(self) -> bool:
        """
        Login using the device code flow.
        
        This method initiates the device code flow, displays the verification URL
        to the user, and polls for authentication status.
        
        Returns:
            True if login was successful, False otherwise
        """
        try:
            # Get device code
            verification_url = await self.client.get_device_code()
            
            # Display instructions to the user
            print("\n=== Tidal Authentication ===")
            print(f"1. Open this URL in your browser: {verification_url}")
            print("2. Log in to your Tidal account")
            print("3. Authorize this application")
            print("4. Wait for the authentication to complete")
            print("===============================\n")
            
            # Poll for authentication status
            timeout = self.client.login_key.authCheckTimeout or 300  # Default to 5 minutes
            interval = self.client.login_key.authCheckInterval or 5  # Default to 5 seconds
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                # Check if the user has authorized the application
                if await self.client.check_auth_status():
                    # Save settings
                    save_settings(self.settings)
                    return True
                
                # Wait before checking again
                print("Waiting for authorization...", end="\r")
                await asyncio.sleep(interval)
            
            # Timeout
            print("\nAuthentication timed out. Please try again.")
            return False
            
        except AuthenticationError as e:
            self.logger.error(f"Authentication error: {str(e)}")
            print(f"Authentication error: {str(e)}")
            return False
        except Exception as e:
            self.logger.exception("Unexpected error during authentication")
            print(f"Unexpected error: {str(e)}")
            return False
    
    async def login_with_token(self, access_token: str, user_id: Optional[str] = None) -> bool:
        """
        Login using an access token.
        
        Args:
            access_token: Access token
            user_id: Optional user ID to verify
            
        Returns:
            True if login was successful, False otherwise
        """
        try:
            await self.client.login_with_token(access_token, user_id)
            save_settings(self.settings)
            return True
        except AuthenticationError as e:
            self.logger.error(f"Authentication error: {str(e)}")
            print(f"Authentication error: {str(e)}")
            return False
        except Exception as e:
            self.logger.exception("Unexpected error during authentication")
            print(f"Unexpected error: {str(e)}")
            return False
    
    async def refresh_token(self) -> bool:
        """
        Refresh the access token.
        
        Returns:
            True if refresh was successful, False otherwise
        """
        if not self.settings.refresh_token:
            self.logger.warning("No refresh token available")
            return False
        
        try:
            result = await self.client.refresh_token(self.settings.refresh_token)
            if result:
                save_settings(self.settings)
                return True
            return False
        except Exception as e:
            self.logger.exception("Error refreshing token")
            return False
    
    async def ensure_logged_in(self) -> bool:
        """
        Ensure the user is logged in.
        
        This method checks if the user is already logged in, and if not,
        attempts to refresh the token or initiate a new login.
        
        Returns:
            True if the user is logged in, False otherwise
        """
        # Check if we have a valid access token
        if self.settings.auth_token and self.settings.token_expiry:
            # Check if the token is still valid
            if time.time() < self.settings.token_expiry - 300:  # 5 minutes buffer
                # Set the token in the client
                self.client.login_key.accessToken = self.settings.auth_token
                self.client.login_key.userId = self.settings.user_id
                self.client.login_key.countryCode = self.settings.country_code
                return True
            
            # Token is expired, try to refresh it
            self.logger.info("Access token expired, attempting to refresh")
            if await self.refresh_token():
                return True
        
        # No valid token, need to log in
        self.logger.info("No valid access token, initiating login")
        return await self.login_with_device_code()
    
    def is_logged_in(self) -> bool:
        """
        Check if the user is logged in.
        
        Returns:
            True if the user is logged in, False otherwise
        """
        return (
            bool(self.settings.auth_token) and 
            bool(self.settings.token_expiry) and 
            time.time() < self.settings.token_expiry
        )
