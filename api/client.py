"""
Tidal API client for RIPTIDAL.

This module provides a client for interacting with the Tidal API.
"""

import asyncio
import base64
import json
import logging
import random
import re
import time
from typing import Dict, List, Optional, Any, Union, Tuple, TypeVar, Type, cast

import aiohttp
from aiohttp import BasicAuth
from pydantic import BaseModel

from riptidal.api.models import (
    Album, Artist, Track, Video, Playlist, StreamUrl, VideoStreamUrl,
    SearchResult, Lyrics, LoginKey, ResourceType, StreamQuality, VideoQuality
)
from riptidal.api.keys import get_key, is_key_valid, get_all_keys
from riptidal.core.settings import Settings
from riptidal.utils.logger import get_logger

T = TypeVar('T', bound=BaseModel)


class TidalError(Exception):
    """Base exception for Tidal API errors."""
    pass


class AuthenticationError(TidalError):
    """Exception raised for authentication errors."""
    pass


class APIError(TidalError):
    """Exception raised for API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, sub_status: Optional[int] = None):
        self.status_code = status_code
        self.sub_status = sub_status
        super().__init__(message)


class ConnectionError(TidalError):
    """Exception raised for connection errors."""
    pass


class TidalClient:
    """
    Asynchronous client for the Tidal API.
    
    This class provides methods for interacting with the Tidal API,
    including authentication, searching, and downloading.
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize the Tidal API client.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = get_logger(__name__)
        
        key_data = get_key(settings.api_key_index)
        self.api_key = {
            'clientId': key_data['clientId'],
            'clientSecret': key_data['clientSecret']
        }
        
        self.logger.info(f"Using API key: {key_data['platform']} - {key_data['formats']}")
        if key_data['valid'] != 'True':
            self.logger.warning(f"Selected API key is marked as invalid. This may cause issues.")
        
        self.login_key = LoginKey()
        # Load authentication data from settings if available
        if settings.country_code:
            self.login_key.countryCode = settings.country_code
        if settings.auth_token:
            self.login_key.accessToken = settings.auth_token
            self.logger.debug(f"Loaded access token from settings")
        self.base_url = "https://api.tidalhifi.com/v1/"
        self.auth_url = "https://auth.tidal.com/v1/oauth2"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Context manager entry."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
    
    async def close(self):
        """Explicitly close the client session."""
        if self.session:
            self.logger.debug("Explicitly closing TidalClient session")
            await self.session.close()
            self.session = None
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get the current session or create a new one."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth: Optional[Tuple[str, str]] = None,
        base_url: Optional[str] = None,
        retry_count: int = 0,
        use_form_data: bool = False
    ) -> Dict[str, Any]:
        """
        Make a request to the Tidal API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            headers: Request headers
            auth: Basic auth credentials (username, password)
            base_url: Override the base URL
            retry_count: Current retry count
            use_form_data: Whether to send data as form-encoded (True) or JSON (False)
            
        Returns:
            Response data as a dictionary
            
        Raises:
            AuthenticationError: If authentication fails
            APIError: If the API returns an error
            ConnectionError: If there's a connection error
        """
        if endpoint and not endpoint.startswith('/'):
            endpoint = '/' + endpoint
            
        if base_url and base_url.endswith('/'):
            base_url = base_url[:-1]
        elif not base_url and self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]
            
        url = f"{base_url or self.base_url}{endpoint}"
        
        if params is None:
            params = {}
        
        if self.login_key.countryCode and 'countryCode' not in params:
            params['countryCode'] = self.login_key.countryCode
        
        if headers is None:
            headers = {}
        
        if self.login_key.accessToken and 'authorization' not in headers:
            headers['authorization'] = f"Bearer {self.login_key.accessToken}"
        
        self.logger.debug(f"API request: {method} {url}")
        self.logger.debug(f"Full URL: {url}")
        self.logger.debug(f"Full request params: {params}")
        if data:
            self.logger.debug(f"Full request data: {data}")
        self.logger.debug(f"Full request headers: {headers}")
        if auth:
            self.logger.debug(f"Auth: {auth[0]} (secret hidden)")
        self.logger.debug(f"Data format: {'form-encoded' if use_form_data else 'JSON'}")
        self.logger.debug(f"Retry count: {retry_count}")
        self.logger.debug(f"Base URL: {base_url or self.base_url}")
        
        try:
            session = self._get_session()
            
            request_kwargs = {
                "method": method,
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": self.settings.connection_timeout,
                "ssl": None
            }
            
            if auth:
                if isinstance(auth, tuple) and len(auth) == 2:
                    request_kwargs["auth"] = BasicAuth(auth[0], auth[1])
                else:
                    request_kwargs["auth"] = auth
            
            if data:
                if use_form_data:
                    request_kwargs["data"] = data
                else:
                    request_kwargs["json"] = data
            
            async with session.request(**request_kwargs) as response:
                self.logger.debug(f"Response status: {response.status}")
                self.logger.debug(f"Response headers: {dict(response.headers)}")
                
                if response.status == 429:
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            wait_time = int(retry_after)
                        except ValueError:
                            wait_time = self.settings.retry_delay * (2 ** retry_count)
                    else:
                        wait_time = self.settings.retry_delay * (2 ** retry_count)
                        jitter = wait_time * 0.2 * (random.random() * 2 - 1)
                        wait_time = max(1, wait_time + jitter)
                    
                    if retry_count >= self.settings.retry_attempts:
                        extended_wait = 30 + (retry_count - self.settings.retry_attempts) * 15
                        wait_time = max(wait_time, extended_wait)
                        self.logger.warning(f"Rate limit exceeded after {self.settings.retry_attempts} attempts. Extended cooldown: waiting {wait_time:.1f} seconds before retry...")
                    else:
                        self.logger.warning(f"Rate limited. Waiting {wait_time:.1f} seconds (attempt {retry_count+1}/{self.settings.retry_attempts})...")
                    
                    await asyncio.sleep(wait_time)
                    return await self._request(
                        method, endpoint, params, data, headers, auth, base_url, retry_count + 1, use_form_data
                    )
                
                response_text = await response.text()
                self.logger.debug(f"Response text: {response_text[:500]}")
                
                try:
                    result = json.loads(response_text)
                    self.logger.debug(f"Parsed JSON response: {json.dumps(result, indent=2)[:2000]}")
                except json.JSONDecodeError:
                    self.logger.error(f"Failed to parse response as JSON: {response_text[:2000]}")
                    raise APIError(f"Invalid JSON response: {response_text[:2000]}", response.status)
                
                if 'status' in result and result['status'] != 200:
                    message = result.get('userMessage', 'Unknown error')
                    sub_status = result.get('subStatus')
                    self.logger.error(f"API error: {message} (status: {result['status']}, subStatus: {sub_status})")
                    self.logger.error(f"Full error response: {json.dumps(result, indent=2)}")
                    raise APIError(message, result['status'], sub_status)
                
                return result
                
        except aiohttp.ClientError as e:
            self.logger.error(f"Connection error: {str(e)}")
            
            wait_time = self.settings.retry_delay * (2 ** retry_count)
            
            if retry_count >= self.settings.retry_attempts:
                extended_wait = 30 + (retry_count - self.settings.retry_attempts) * 15
                wait_time = max(wait_time, extended_wait)
                self.logger.warning(f"Connection error after {self.settings.retry_attempts} attempts. Extended cooldown: waiting {wait_time:.1f} seconds before retry...")
            else:
                self.logger.info(f"Connection error. Retrying in {wait_time:.1f} seconds (attempt {retry_count+1}/{self.settings.retry_attempts})...")
            
            await asyncio.sleep(wait_time)
            return await self._request(
                method, endpoint, params, data, headers, auth, base_url, retry_count + 1, use_form_data
            )
    
    async def _get(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Make a GET request to the Tidal API."""
        return await self._request("GET", endpoint, params=params, **kwargs)
    
    async def _post(
        self, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        use_form_data: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make a POST request to the Tidal API.
        
        Args:
            endpoint: API endpoint
            data: Request body data
            use_form_data: Whether to send data as form-encoded (True) or JSON (False)
            **kwargs: Additional arguments for _request
            
            Returns:
            Response data as a dictionary
        """
        if endpoint.startswith('/device_authorization') or endpoint.startswith('/token'):
            use_form_data = True
            
        headers = kwargs.get('headers', {})
        if use_form_data:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            kwargs['headers'] = headers
            
        return await self._request("POST", endpoint, data=data, use_form_data=use_form_data, **kwargs)
    
    async def _get_items(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Get paginated items from the Tidal API.
        
        This method handles pagination automatically, fetching all items
        across multiple pages.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            **kwargs: Additional arguments for _request
            
        Returns:
            List of items
        """
        if params is None:
            params = {}
        
        params['limit'] = 50
        params['offset'] = 0
        
        items = []
        total = None
        
        while True:
            data = await self._get(endpoint, params, **kwargs)
            
            if 'totalNumberOfItems' in data:
                total = data['totalNumberOfItems']
            
            if 'items' not in data:
                self.logger.warning(f"No items found in response: {data}")
                break
            
            batch_items = data['items']
            self.logger.debug(f"Pagination page: offset={params.get('offset', 0)} limit={params.get('limit', 50)} page_size={len(batch_items)}")
            items.extend(batch_items)
            
            if total is not None and len(items) >= total:
                self.logger.debug(f"Pagination complete: collected {len(items)} of {total} items")
                break

            # Continue until an empty page is returned; some endpoints may return short pages even when more remain
            if len(batch_items) == 0:
                self.logger.debug("Pagination reached empty page; stopping")
                break

            params['offset'] += len(batch_items)
            self.logger.debug(f"Pagination: next offset={params['offset']} (page_size={len(batch_items)}, total={total})")
        
        return items
    
    def _parse_model(self, data: Dict[str, Any], model_class: Type[T]) -> T:
        """
        Parse API response data into a model.
        
        Args:
            data: Response data
            model_class: Model class to parse into
            
        Returns:
            Parsed model instance
        """
        try:
            return model_class(**data)
        except Exception as e:
            self.logger.error(f"Error parsing {model_class.__name__}: {str(e)}")
            self.logger.debug(f"Data: {data}")
            raise
    
    async def get_device_code(self) -> str:
        """
        Get a device code for authentication.
        
        Returns:
            Verification URL with user code
        """
        data = {
            'client_id': self.api_key['clientId'],
            'scope': 'r_usr+w_usr+w_sub'
        }
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        url = f"{self.auth_url}/device_authorization"
        
        self.logger.debug(f"Device code request: POST {url}")
        self.logger.debug(f"Device code data: {data}")
        
        try:
            session = self._get_session()
            async with session.post(
                url=url,
                data=data,
                headers=headers,
                ssl=None
            ) as response:
                response_text = await response.text()
                self.logger.debug(f"Device code response status: {response.status}")
                self.logger.debug(f"Device code response: {response_text[:500]}")
                
                if response.status != 200:
                    self.logger.error(f"Device code error: Status {response.status}")
                    self.logger.error(f"Response: {response_text[:200]}")
                    raise AuthenticationError(f"Device authorization failed with status {response.status}")
                
                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError:
                    self.logger.error(f"Failed to parse device code response: {response_text[:200]}")
                    raise AuthenticationError("Failed to parse device code response")
                
                if 'status' in result and result['status'] != 200:
                    self.logger.error(f"Device code API error: {result.get('userMessage', 'Unknown error')}")
                    raise AuthenticationError("Device authorization failed. Please try again.")
        except aiohttp.ClientError as e:
            self.logger.error(f"Device code request error: {str(e)}")
            raise AuthenticationError(f"Device authorization failed: {str(e)}")
        
        try:
            self.login_key.deviceCode = result['deviceCode']
            self.login_key.userCode = result['userCode']
            self.login_key.verificationUrl = result['verificationUri']
            self.login_key.authCheckTimeout = result['expiresIn']
            self.login_key.authCheckInterval = result['interval']
            
            return f"http://{self.login_key.verificationUrl}/{self.login_key.userCode}"
        except KeyError as e:
            self.logger.error(f"Missing key in device code response: {str(e)}")
            self.logger.debug(f"Device code response: {result}")
            raise AuthenticationError(f"Invalid device code response: missing {str(e)}")
    
    async def check_auth_status(self) -> bool:
        """
        Check the authentication status.
        
        Returns:
            True if authentication is successful, False otherwise
        """
        if not self.login_key.deviceCode:
            self.logger.error("No device code available. Call get_device_code first.")
            return False
            
        data = {
            'client_id': self.api_key['clientId'],
            'device_code': self.login_key.deviceCode,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'scope': 'r_usr+w_usr+w_sub'
        }
        
        auth = (self.api_key['clientId'], self.api_key['clientSecret'])
        
        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            url = f"{self.auth_url}/token"
            
            self.logger.debug(f"Auth request: POST {url}")
            self.logger.debug(f"Auth data: {data}")
            
            session = self._get_session()
            async with session.post(
                url=url,
                data=data,
                auth=BasicAuth(auth[0], auth[1]),
                headers=headers,
                ssl=None
            ) as response:
                response_text = await response.text()
                self.logger.debug(f"Auth response status: {response.status}")
                self.logger.debug(f"Auth response: {response_text[:500]}")
                
                if response.status != 200:
                    try:
                        result = json.loads(response_text)
                        if result.get('status') == 400 and result.get('sub_status') == 1002:
                            return False
                        self.logger.error(f"Auth error: {result.get('userMessage', 'Unknown error')}")
                    except json.JSONDecodeError:
                        self.logger.error(f"Failed to parse auth response: {response_text[:200]}")
                    return False
                
                result = json.loads(response_text)
        except Exception as e:
            self.logger.error(f"Error checking auth status: {str(e)}")
            return False
        
        try:
            self.login_key.userId = result['user']['userId']
            self.login_key.countryCode = result['user']['countryCode']
            self.login_key.accessToken = result['access_token']
            self.login_key.refreshToken = result['refresh_token']
            self.login_key.expiresIn = result['expires_in']
            
            self.settings.auth_token = self.login_key.accessToken
            self.settings.refresh_token = self.login_key.refreshToken
            self.settings.token_expiry = int(time.time()) + self.login_key.expiresIn
            self.settings.user_id = str(self.login_key.userId)
            self.settings.country_code = self.login_key.countryCode
            
            self.logger.info(f"Successfully authenticated as user {self.login_key.userId}")
            return True
        except KeyError as e:
            self.logger.error(f"Missing key in auth response: {str(e)}")
            self.logger.debug(f"Auth response: {result}")
            return False
    
    async def login_with_token(self, access_token: str, user_id: Optional[str] = None) -> None:
        """
        Login with an access token.
        
        Args:
            access_token: Access token
            user_id: Optional user ID to verify
            
        Raises:
            AuthenticationError: If authentication fails
        """
        headers = {'authorization': f"Bearer {access_token}"}
        
        try:
            result = await self._request(
                "GET", 
                'sessions', 
                headers=headers, 
                base_url=self.base_url
            )
        except APIError as e:
            raise AuthenticationError(f"Login failed: {str(e)}")
        
        if user_id and str(result['userId']) != str(user_id):
            raise AuthenticationError("User ID mismatch. Please use your own access token.")
        
        self.login_key.userId = result['userId']
        self.login_key.countryCode = result['countryCode']
        self.login_key.accessToken = access_token
        
        self.settings.auth_token = access_token
        self.settings.user_id = str(self.login_key.userId)
        self.settings.country_code = self.login_key.countryCode
    
    async def refresh_token(self, refresh_token: str) -> bool:
        """
        Refresh an access token.
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            True if successful, False otherwise
        """
        data = {
            'client_id': self.api_key['clientId'],
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
            'scope': 'r_usr+w_usr+w_sub'
        }
        
        auth = (self.api_key['clientId'], self.api_key['clientSecret'])
        
        try:
            result = await self._post(
                '/token', 
                data=data, 
                auth=auth, 
                base_url=self.auth_url
            )
        except APIError:
            return False
        
        self.login_key.userId = result['user']['userId']
        self.login_key.countryCode = result['user']['countryCode']
        self.login_key.accessToken = result['access_token']
        self.login_key.expiresIn = result['expires_in']
        
        self.settings.auth_token = self.login_key.accessToken
        self.settings.token_expiry = int(time.time()) + self.login_key.expiresIn
        self.settings.user_id = str(self.login_key.userId)
        self.settings.country_code = self.login_key.countryCode
        
        return True
    
    async def get_album(self, album_id: str) -> Album:
        """
        Get album details.
        
        Args:
            album_id: Album ID
            
        Returns:
            Album object
        """
        self.logger.debug(f"Fetching album details for ID: {album_id}")
        data = await self._get(f'albums/{album_id}')
        
        self.logger.debug(f"Album data received: {json.dumps(data, indent=2)[:500]}")
        
        if 'title' not in data or not data['title']:
            self.logger.warning(f"Album {album_id} has no title in API response")
            data['title'] = f"Album {album_id}"
        
        album = self._parse_model(data, Album)
        self.logger.debug(f"Parsed album: {album.title} (ID: {album.id})")
        return album
    
    async def get_track(self, track_id: str) -> Track:
        """
        Get track details.
        
        Args:
            track_id: Track ID
            
        Returns:
            Track object
        """
        data = await self._get(f'tracks/{track_id}')
        return self._parse_model(data, Track)
    
    async def get_artist(self, artist_id: str) -> Artist:
        """
        Get artist details.
        
        Args:
            artist_id: Artist ID
            
        Returns:
            Artist object
        """
        data = await self._get(f'artists/{artist_id}')
        return self._parse_model(data, Artist)
    
    async def get_playlist(self, playlist_id: str) -> Playlist:
        """
        Get playlist details.
        
        Args:
            playlist_id: Playlist ID
            
        Returns:
            Playlist object
        """
        data = await self._get(f'playlists/{playlist_id}')
        return self._parse_model(data, Playlist)
    
    async def get_video(self, video_id: str) -> Video:
        """
        Get video details.
        
        Args:
            video_id: Video ID
            
        Returns:
            Video object
        """
        data = await self._get(f'videos/{video_id}')
        return self._parse_model(data, Video)
    
    async def get_user_playlists(self) -> List[Playlist]:
        """
        Get the user's playlists.
        
        Returns:
            List of Playlist objects
        """
        self.logger.info(f"Fetching playlists for user {self.login_key.userId}")
        
        items = await self._get_items(f'users/{self.login_key.userId}/playlists')
        
        self.logger.debug(f"Received {len(items)} playlist items from API")
        
        playlists = []
        for i, item in enumerate(items):
            try:
                self.logger.debug(f"Processing playlist {i+1}/{len(items)} with UUID: {item.get('uuid', 'unknown')}")
                playlist = self._parse_model(item, Playlist)
                
                self.logger.debug(f"Playlist {i+1}: {playlist.title} ({playlist.numberOfTracks} tracks)")
                
                playlists.append(playlist)
            except Exception as e:
                self.logger.error(f"Error processing playlist {i+1}: {str(e)}")
        
        self.logger.info(f"Successfully processed {len(playlists)} playlists")
        return playlists
    
    async def get_album_tracks(self, album_id: str) -> List[Track]:
        """
        Get tracks from an album.
        
        Args:
            album_id: Album ID
            
        Returns:
            List of Track objects
        """
        self.logger.info(f"Fetching tracks for album {album_id}")
        
        items = await self._get_items(f'albums/{album_id}/tracks')
        
        self.logger.debug(f"Received {len(items)} track items from API")
        
        try:
            album = await self.get_album(album_id)
            self.logger.debug(f"Got album details: {album.title}")
        except Exception as e:
            self.logger.error(f"Failed to get album details for {album_id}: {str(e)}")
            album = None
        
        tracks = []
        for i, item in enumerate(items):
            try:
                self.logger.debug(f"Processing track {i+1}/{len(items)} with ID: {item.get('id', 'unknown')}")
                track = self._parse_model(item, Track)
                
                if album:
                    track.album = album
                
                self.logger.debug(f"Track {i+1}: {track.title} by {track.artist_names}")
                
                tracks.append(track)
            except Exception as e:
                self.logger.error(f"Error processing track {i+1}: {str(e)}")
        
        self.logger.info(f"Successfully processed {len(tracks)} tracks from album {album_id}")
        return tracks
    
    async def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """
        Get tracks from a playlist.
        
        Args:
            playlist_id: Playlist ID
            
        Returns:
            List of Track objects
        """
        self.logger.info(f"Fetching tracks for playlist {playlist_id}")
        
        items = await self._get_items(f'playlists/{playlist_id}/tracks')
        
        self.logger.debug(f"Received {len(items)} track items from API")
        
        tracks = []
        for i, item in enumerate(items):
            try:
                self.logger.debug(f"Processing track {i+1}/{len(items)} with ID: {item.get('id', 'unknown')}")
                track = self._parse_model(item, Track)
                
                self.logger.debug(f"Track {i+1}: {track.title} by {track.artist_names}")
                
                tracks.append(track)
            except Exception as e:
                self.logger.error(f"Error processing track {i+1}: {str(e)}")
        
        self.logger.info(f"Successfully processed {len(tracks)} tracks from playlist {playlist_id}")
        return tracks
    
    async def probe_track_qualities(self, track_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Probe all available qualities for a track without downloading it.
        
        This method attempts to get stream URLs for all quality levels and returns
        detailed information about which qualities are available and their properties.
        
        Args:
            track_id: Track ID to probe
            
        Returns:
            Dictionary mapping quality names to details about that quality
        """
        self.logger.info(f"Probing available qualities for track {track_id}")
        
        # Define all qualities to test
        qualities_to_test = [
            StreamQuality.LOW,
            StreamQuality.HIGH,
            StreamQuality.LOSSLESS,
            StreamQuality.HI_RES,
        ]
        
        # Map API quality values to more readable descriptions
        quality_descriptions = {
            "LOW": "Low Quality (AAC, 96kbps)",
            "HIGH": "High Quality (AAC, 320kbps)",
            "LOSSLESS": "Lossless (FLAC, 16-bit/44.1kHz)",
            "HI_RES": "High Resolution (FLAC, 24-bit/96kHz)",
            "HI_RES_LOSSLESS": "Master Quality (MQA, up to 24-bit/192kHz)"
        }
        
        # Quality mapping for API requests
        quality_map = {
            StreamQuality.LOW: "LOW",
            StreamQuality.HIGH: "HIGH",
            StreamQuality.LOSSLESS: "LOSSLESS",
            StreamQuality.HI_RES: "HI_RES",
            StreamQuality.MAX: "HI_RES_LOSSLESS"
        }
        
        results = {}
        
        # Try each quality
        for quality in qualities_to_test:
            api_quality = quality_map.get(quality, "HIGH")
            self.logger.debug(f"Testing quality {quality.name} (API: {api_quality})")
            
            try:
                params = {
                    "audioquality": api_quality,
                    "playbackmode": "STREAM",
                    "assetpresentation": "FULL"
                }
                
                data = await self._get(f'tracks/{track_id}/playbackinfopostpaywall', params)
                
                # Extract useful information
                actual_quality = data.get('audioQuality', 'Unknown')
                manifest_type = data.get('manifestMimeType', 'Unknown')
                
                # Parse manifest to get more details
                codec = "Unknown"
                sample_rate = "Unknown"
                bit_depth = "Unknown"
                
                if "vnd.tidal.bt" in manifest_type:
                    manifest_bytes = base64.b64decode(data['manifest'])
                    manifest = json.loads(manifest_bytes.decode('utf-8'))
                    codec = manifest.get('codecs', 'Unknown')
                    
                    # Try to extract sample rate and bit depth from codec string
                    if codec != "Unknown":
                        # Example codec: "FLAC 24bit / 96kHz"
                        if "FLAC" in codec and "bit" in codec and "kHz" in codec:
                            bit_match = re.search(r'(\d+)bit', codec)
                            if bit_match:
                                bit_depth = f"{bit_match.group(1)}-bit"
                            
                            rate_match = re.search(r'(\d+)kHz', codec)
                            if rate_match:
                                sample_rate = f"{rate_match.group(1)}kHz"
                        elif "AAC" in codec:
                            # For AAC, we don't have bit depth/sample rate in the same way
                            if "HIGH" in actual_quality:
                                bit_depth = "16-bit equivalent"
                                sample_rate = "44.1kHz equivalent"
                            else:
                                bit_depth = "Low quality"
                                sample_rate = "Low quality"
                
                # Store the results
                results[quality.name] = {
                    "available": True,
                    "requested_quality": quality.name,
                    "api_quality_param": api_quality,
                    "actual_quality": actual_quality,
                    "description": quality_descriptions.get(actual_quality, "Unknown Quality"),
                    "manifest_type": manifest_type,
                    "codec": codec,
                    "sample_rate": sample_rate,
                    "bit_depth": bit_depth
                }
                
                self.logger.debug(f"Quality {quality.name} is available with actual quality {actual_quality}")
                
            except Exception as e:
                self.logger.debug(f"Quality {quality.name} is not available: {str(e)}")
                results[quality.name] = {
                    "available": False,
                    "requested_quality": quality.name,
                    "api_quality_param": api_quality,
                    "error": str(e)
                }
        
        # Also try MAX quality which should attempt to get the highest available
        try:
            stream = await self.get_stream_url(track_id, StreamQuality.MAX)
            results["MAX"] = {
                "available": True,
                "requested_quality": "MAX",
                "api_quality_param": "HI_RES_LOSSLESS",
                "actual_quality": stream.soundQuality,
                "description": quality_descriptions.get(stream.soundQuality, "Unknown Quality"),
                "codec": stream.codec,
                "sample_rate": "Unknown",  # We'd need to parse this from codec
                "bit_depth": "Unknown"     # We'd need to parse this from codec
            }
            
            # Try to extract sample rate and bit depth from codec string
            if stream.codec and "FLAC" in stream.codec:
                bit_match = re.search(r'(\d+)bit', stream.codec)
                if bit_match:
                    results["MAX"]["bit_depth"] = f"{bit_match.group(1)}-bit"
                
                rate_match = re.search(r'(\d+)kHz', stream.codec)
                if rate_match:
                    results["MAX"]["sample_rate"] = f"{rate_match.group(1)}kHz"
            
            self.logger.debug(f"MAX quality resulted in {stream.soundQuality} with codec {stream.codec}")
            
        except Exception as e:
            self.logger.debug(f"MAX quality is not available: {str(e)}")
            results["MAX"] = {
                "available": False,
                "requested_quality": "MAX",
                "api_quality_param": "HI_RES_LOSSLESS",
                "error": str(e)
            }
        
        # Add a summary of the highest available quality
        highest_quality = None
        for quality in ["HI_RES", "LOSSLESS", "HIGH", "LOW"]:
            if quality in results and results[quality]["available"]:
                highest_quality = quality
                break
        
        if highest_quality:
            results["summary"] = {
                "highest_available_quality": highest_quality,
                "highest_quality_details": results[highest_quality]
            }
        else:
            results["summary"] = {
                "highest_available_quality": None,
                "error": "No qualities available"
            }
        
        return results
    
    async def get_favorite_tracks(self) -> List[Track]:
        """
        Get the user's favorite tracks.
        
        Returns:
            List of Track objects
        """
        self.logger.info(f"Fetching favorite tracks for user {self.login_key.userId}")
        
        items = await self._get_items(f'users/{self.login_key.userId}/favorites/tracks')
        
        self.logger.debug(f"Received {len(items)} favorite track items from API")
        
        tracks = []
        for i, item in enumerate(items):
            try:
                if isinstance(item, dict) and 'item' in item:
                    track_data = item['item']
                    self.logger.debug(f"Processing track {i+1}/{len(items)} with ID: {track_data.get('id', 'unknown')}")
                    track = self._parse_model(track_data, Track)
                    
                    self.logger.debug(f"Track {i+1}: {track.title} by {track.artist_names}")
                    
                    if track.album is None or track.album.id is None:
                        self.logger.warning(f"Track '{track.title}' (ID: {track.id}) has no album information")
                    
                    tracks.append(track)
                else:
                    self.logger.warning(f"Item {i+1} has unexpected format: {item}")
            except Exception as e:
                self.logger.error(f"Error processing track {i+1}: {str(e)}")
        
        self.logger.info(f"Successfully processed {len(tracks)} favorite tracks")
        return tracks
    
    async def get_favorite_albums(self) -> List[Album]:
        """
        Get the user's favorite albums.
        
        Returns:
            List of Album objects
        """
        self.logger.info(f"Fetching favorite albums for user {self.login_key.userId}")
        
        items = await self._get_items(f'users/{self.login_key.userId}/favorites/albums')
        
        self.logger.debug(f"Received {len(items)} favorite album items from API")
        
        albums = []
        for i, item in enumerate(items):
            try:
                if isinstance(item, dict) and 'item' in item:
                    album_data = item['item']
                    self.logger.debug(f"Processing album {i+1}/{len(items)} with ID: {album_data.get('id', 'unknown')}")
                    album = self._parse_model(album_data, Album)
                    
                    self.logger.debug(f"Album {i+1}: {album.title}")
                    
                    albums.append(album)
                else:
                    self.logger.warning(f"Item {i+1} has unexpected format: {item}")
            except Exception as e:
                self.logger.error(f"Error processing album {i+1}: {str(e)}")
        
        self.logger.info(f"Successfully processed {len(albums)} favorite albums")
        return albums
    
    async def get_favorite_artists(self) -> List[Artist]:
        """
        Get the user's favorite artists.
        
        Returns:
            List of Artist objects
        """
        self.logger.info(f"Fetching favorite artists for user {self.login_key.userId}")
        
        items = await self._get_items(f'users/{self.login_key.userId}/favorites/artists')
        
        self.logger.debug(f"Received {len(items)} favorite artist items from API")
        
        artists = []
        for i, item in enumerate(items):
            try:
                if isinstance(item, dict) and 'item' in item:
                    artist_data = item['item']
                    self.logger.debug(f"Processing artist {i+1}/{len(items)} with ID: {artist_data.get('id', 'unknown')}")
                    artist = self._parse_model(artist_data, Artist)
                    
                    self.logger.debug(f"Artist {i+1}: {artist.name}")
                    
                    artists.append(artist)
                else:
                    self.logger.warning(f"Item {i+1} has unexpected format: {item}")
            except Exception as e:
                self.logger.error(f"Error processing artist {i+1}: {str(e)}")
        
        self.logger.info(f"Successfully processed {len(artists)} favorite artists")
        return artists
    
    async def get_favorite_videos(self) -> List[Video]:
        """
        Get the user's favorite videos.
        
        Returns:
            List of Video objects
        """
        self.logger.info(f"Fetching favorite videos for user {self.login_key.userId}")
        
        items = await self._get_items(f'users/{self.login_key.userId}/favorites/videos')
        
        self.logger.debug(f"Received {len(items)} favorite video items from API")
        
        videos = []
        for i, item in enumerate(items):
            try:
                if isinstance(item, dict) and 'item' in item:
                    video_data = item['item']
                    self.logger.debug(f"Processing video {i+1}/{len(items)} with ID: {video_data.get('id', 'unknown')}")
                    video = self._parse_model(video_data, Video)
                    
                    self.logger.debug(f"Video {i+1}: {video.title}")
                    
                    videos.append(video)
                else:
                    self.logger.warning(f"Item {i+1} has unexpected format: {item}")
            except Exception as e:
                self.logger.error(f"Error processing video {i+1}: {str(e)}")
        
        self.logger.info(f"Successfully processed {len(videos)} favorite videos")
        return videos
    
    async def get_artist_videos(self, artist_id: str) -> List[Video]:
        """
        Get videos from an artist.
        
        Args:
            artist_id: Artist ID
            
        Returns:
            List of Video objects
        """
        self.logger.info(f"Fetching videos for artist {artist_id}")
        
        items = await self._get_items(f'artists/{artist_id}/videos')
        
        self.logger.debug(f"Received {len(items)} video items from API")
        
        videos = []
        for i, item in enumerate(items):
            try:
                self.logger.debug(f"Processing video {i+1}/{len(items)} with ID: {item.get('id', 'unknown')}")
                video = self._parse_model(item, Video)
                
                self.logger.debug(f"Video {i+1}: {video.title}")
                
                videos.append(video)
            except Exception as e:
                self.logger.error(f"Error processing video {i+1}: {str(e)}")
        
        self.logger.info(f"Successfully processed {len(videos)} videos from artist {artist_id}")
        return videos
    
    async def get_stream_url(self, track_id: str, quality: StreamQuality) -> StreamUrl:
        """
        Get the stream URL for a track with better error handling and quality fallback.
        
        This method closely follows the reference implementation's approach.
        
        Args:
            track_id: Track ID
            quality: Stream quality
            
        Returns:
            StreamUrl object
        """
        self.logger.debug(f"Getting stream URL for track {track_id} with quality {quality}")
        
        quality_order = [
            StreamQuality.MAX,
            StreamQuality.HI_RES,
            StreamQuality.LOSSLESS,
            StreamQuality.HIGH,
            StreamQuality.LOW
        ]
        
        quality_map = {
            StreamQuality.LOW: "LOW",
            StreamQuality.HIGH: "HIGH",
            StreamQuality.LOSSLESS: "LOSSLESS",
            StreamQuality.HI_RES: "HI_RES",
            StreamQuality.MAX: "HI_RES_LOSSLESS"
        }
        
        start_index = 0
        if quality != StreamQuality.MAX:
            try:
                start_index = quality_order.index(quality)
                self.logger.debug(f"Starting with quality index {start_index}: {quality_order[start_index]}")
            except ValueError:
                self.logger.warning(f"Quality {quality} not found in quality order, starting with highest quality")
                start_index = 0
        else:
            self.logger.debug(f"MAX quality requested, starting with highest quality: {quality_order[0]}")
        
        last_error = None
        for i in range(start_index, len(quality_order)):
            try:
                current_quality = quality_order[i]
                self.logger.debug(f"Trying quality {current_quality}")
                
                api_quality = quality_map.get(current_quality, "HIGH")
                self.logger.debug(f"Mapped quality {current_quality} to API quality {api_quality}")
                
                params = {
                    "audioquality": api_quality,
                    "playbackmode": "STREAM",
                    "assetpresentation": "FULL"
                }
                
                self.logger.debug(f"Requesting playback info with params: {params}")
                
                try:
                    data = await self._get(f'tracks/{track_id}/playbackinfopostpaywall', params)
                    
                    self.logger.debug(f"Received playback info for track {track_id}")
                    self.logger.debug(f"Audio quality: {data.get('audioQuality', 'unknown')}")
                    self.logger.debug(f"Manifest MIME type: {data.get('manifestMimeType', 'unknown')}")
                    
                    resp = StreamUrl(
                        trackid=data['trackId'],
                        soundQuality=data['audioQuality'],
                        url=""
                    )
                    
                    manifest_type = data['manifestMimeType']
                    self.logger.debug(f"Processing manifest of type: {manifest_type}")
                    
                    if "vnd.tidal.bt" in manifest_type:
                        self.logger.debug("Processing binary manifest")
                        manifest_bytes = base64.b64decode(data['manifest'])
                        manifest = json.loads(manifest_bytes.decode('utf-8'))
                        self.logger.debug(f"Decoded binary manifest: {json.dumps(manifest, indent=2)[:500]}")
                        
                        resp.codec = manifest['codecs']
                        resp.encryptionKey = manifest.get('keyId', "")
                        resp.url = manifest['urls'][0]
                        resp.urls = [resp.url]
                        
                        self.logger.debug(f"Extracted codec: {resp.codec}")
                        self.logger.debug(f"Extracted URL: {resp.url}")
                        if resp.encryptionKey:
                            self.logger.debug("Stream is encrypted")
                    elif "dash+xml" in manifest_type:
                        self.logger.debug("Processing DASH manifest")
                        xml_data = base64.b64decode(data['manifest']).decode('utf-8')
                        self.logger.debug(f"Decoded DASH manifest (first 500 chars): {xml_data[:500]}")
                        
                        if 'codecs="' in xml_data:
                            resp.codec = xml_data.split('codecs="')[1].split('"')[0]
                            self.logger.debug(f"Extracted codec: {resp.codec}")
                        else:
                            self.logger.warning("Could not find codec information in DASH manifest")
                        
                        resp.encryptionKey = ""
                        
                        urls = []
                        for line in xml_data.split('\n'):
                            if '<BaseURL>' in line and '</BaseURL>' in line:
                                url = line.split('<BaseURL>')[1].split('</BaseURL>')[0]
                                urls.append(url)
                        
                        self.logger.debug(f"Extracted {len(urls)} URLs from DASH manifest")
                        if urls:
                            self.logger.debug(f"First URL: {urls[0]}")
                            resp.urls = urls
                            resp.url = urls[0]
                        else:
                            self.logger.warning("No URLs found in DASH manifest")
                            raise APIError("No URLs found in DASH manifest")
                    else:
                        self.logger.error(f"Unsupported manifest type: {manifest_type}")
                        raise APIError(f"Unsupported manifest type: {manifest_type}")
                    
                except APIError as e:
                    self.logger.error(f"API error getting stream URL: {str(e)}")
                    raise
                
                if i > start_index:
                    self.logger.info(
                        f"Fallback: Using {current_quality} quality instead of {quality_order[start_index]}"
                    )
                
                self.logger.debug(f"Successfully got stream URL: {resp.url}")
                self.logger.debug(f"Stream quality: {resp.soundQuality}")
                self.logger.debug(f"Stream codec: {resp.codec}")
                return resp
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"Failed to get stream URL with quality {current_quality}: {str(e)}")
                
                if isinstance(e, APIError) and hasattr(e, 'status_code') and e.status_code == 404:
                    if hasattr(e, 'sub_status') and e.sub_status == 2001:
                        self.logger.warning(f"Track {track_id} not available with quality {current_quality}, trying next quality")
                        continue
                
                continue
        
        self.logger.error(f"Failed to get stream URL for track {track_id} at any quality level: {str(last_error)}")
        raise last_error or APIError(f"Failed to get stream URL for track {track_id} at any quality level")
    
    async def _try_get_stream_url(self, track_id: str, quality: StreamQuality) -> StreamUrl:
        """
        Try to get the stream URL for a track at a specific quality without fallback.
        
        Args:
            track_id: Track ID
            quality: Stream quality
            
        Returns:
            StreamUrl object
        """
        self.logger.debug(f"Attempting to get stream URL for track {track_id} with quality {quality}")
        
        params = {
            "audioquality": quality,
            "playbackmode": "STREAM",
            "assetpresentation": "FULL"
        }
        
        self.logger.debug(f"Requesting playback info with params: {params}")
        data = await self._get(f'tracks/{track_id}/playbackinfopostpaywall', params)
        
        self.logger.debug(f"Received playback info for track {track_id}")
        self.logger.debug(f"Audio quality: {data.get('audioQuality', 'unknown')}")
        self.logger.debug(f"Manifest MIME type: {data.get('manifestMimeType', 'unknown')}")
        
        resp = StreamUrl(
            trackid=data['trackId'],
            soundQuality=data['audioQuality'],
            url=""
        )
        
        manifest_type = data['manifestMimeType']
        self.logger.debug(f"Processing manifest of type: {manifest_type}")
        
        if "vnd.tidal.bt" in manifest_type:
            self.logger.debug("Processing binary manifest")
            try:
                manifest_bytes = base64.b64decode(data['manifest'])
                manifest = json.loads(manifest_bytes.decode('utf-8'))
                self.logger.debug(f"Decoded binary manifest: {json.dumps(manifest, indent=2)[:500]}")
                
                resp.codec = manifest['codecs']
                resp.encryptionKey = manifest.get('keyId', "")
                resp.url = manifest['urls'][0]
                resp.urls = [resp.url]
                
                self.logger.debug(f"Extracted codec: {resp.codec}")
                self.logger.debug(f"Extracted URL: {resp.url}")
                if resp.encryptionKey:
                    self.logger.debug("Stream is encrypted")
                
                return resp
            except Exception as e:
                self.logger.error(f"Error processing binary manifest: {str(e)}")
                raise
                
        elif "dash+xml" in manifest_type:
            self.logger.debug("Processing DASH manifest")
            try:
                xml_data = base64.b64decode(data['manifest']).decode('utf-8')
                self.logger.debug(f"Decoded DASH manifest (first 500 chars): {xml_data[:500]}")
                
                if 'codecs="' in xml_data:
                    resp.codec = xml_data.split('codecs="')[1].split('"')[0]
                    self.logger.debug(f"Extracted codec: {resp.codec}")
                else:
                    self.logger.warning("Could not find codec information in DASH manifest")
                
                resp.encryptionKey = ""
                
                urls = []
                for line in xml_data.split('\n'):
                    if '<BaseURL>' in line and '</BaseURL>' in line:
                        url = line.split('<BaseURL>')[1].split('</BaseURL>')[0]
                        urls.append(url)
                
                self.logger.debug(f"Extracted {len(urls)} URLs from DASH manifest")
                if urls:
                    self.logger.debug(f"First URL: {urls[0]}")
                
                resp.urls = urls
                if urls:
                    resp.url = urls[0]
                else:
                    self.logger.warning("No URLs found in DASH manifest")
                
                return resp
            except Exception as e:
                self.logger.error(f"Error processing DASH manifest: {str(e)}")
                raise
        
        self.logger.error(f"Unsupported manifest type: {manifest_type}")
        raise APIError(f"Unsupported manifest type: {manifest_type}")
    
    async def get_lyrics(self, track_id: str) -> Optional[Lyrics]:
        """
        Get lyrics for a track.
        
        Args:
            track_id: Track ID
            
        Returns:
            Lyrics object or None if not available
        """
        try:
            data = await self._get(
                f'tracks/{track_id}/lyrics',
                base_url="https://listen.tidal.com/v1/"
            )
            return self._parse_model(data, Lyrics)
        except APIError:
            return None
    
    async def search(
        self,
        query: str,
        types: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Optional[SearchResult]:
        """
        Search for content on Tidal.
        
        Args:
            query: Search query
            types: List of types to search for (artist, album, track, video, playlist)
            limit: Maximum number of results per type
            offset: Offset for pagination
            
        Returns:
            SearchResult object or None
        """
        # Define valid search types
        valid_types = ['artists', 'albums', 'tracks', 'videos', 'playlists']
        
        # Default to tracks if no type specified
        if not types:
            types = ['track']
        
        # Convert singular to plural and ensure valid type
        type_mapping = {
            'artist': 'artists',
            'album': 'albums',
            'track': 'tracks',
            'video': 'videos',
            'playlist': 'playlists'
        }
        
        # Use only the first type for the endpoint (simpler approach)
        search_type = types[0]
        endpoint_type = type_mapping.get(search_type, search_type + 's')
        
        if endpoint_type not in valid_types:
            self.logger.error(f"Invalid search type: {endpoint_type}")
            return None
        
        # URL encode the query
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        
        # Build parameters
        params = {
            'limit': limit,
            'offset': offset
        }
        
        # Add countryCode if available
        if self.login_key.countryCode:
            params['countryCode'] = self.login_key.countryCode
        
        self.logger.info(f"Searching Tidal for: {query} (type: {endpoint_type})")
        
        try:
            # Use the simpler endpoint format: /search/{type}?query=...
            endpoint = f'search/{endpoint_type}'
            params['query'] = query  # Add query as a parameter instead of in the URL
            
            data = await self._get(endpoint, params)
            
            # Create a SearchResult-compatible structure
            search_result = {
                'artists': {'items': []},
                'albums': {'items': []},
                'tracks': {'items': []},
                'videos': {'items': []},
                'playlists': {'items': []}
            }
            
            # Add the results to the appropriate section
            if 'items' in data:
                search_result[endpoint_type]['items'] = data['items']
                self.logger.debug(f"Found {len(data['items'])} {endpoint_type}")
            else:
                self.logger.warning(f"No 'items' field in search response for {endpoint_type}")
                self.logger.debug(f"Response data keys: {data.keys()}")
            
            return self._parse_model(search_result, SearchResult)
        except APIError as e:
            self.logger.error(f"Search error: {str(e)}")
            return None
    
    async def get_video_stream_url(self, video_id: str, quality: VideoQuality) -> VideoStreamUrl:
        """
        Get the stream URL for a video.
        
        Args:
            video_id: Video ID
            quality: Video quality
            
        Returns:
            VideoStreamUrl object
        """
        self.logger.debug(f"Getting stream URL for video {video_id} with quality {quality}")
        
        quality_value = quality.value
        
        params = {
            "videoquality": "HIGH", 
            "playbackmode": "STREAM",
            "assetpresentation": "FULL"
        }
        
        self.logger.debug(f"Requesting playback info with params: {params}")
        
        try:
            data = await self._get(f'videos/{video_id}/playbackinfopostpaywall', params)
            
            self.logger.debug(f"Received playback info for video {video_id}")
            self.logger.debug(f"Manifest MIME type: {data.get('manifestMimeType', 'unknown')}")
            
            manifest_type = data.get('manifestMimeType', '')
            
            if "vnd.tidal.emu" in manifest_type:
                self.logger.debug("Processing EMU manifest")
                manifest_bytes = base64.b64decode(data['manifest'])
                manifest = json.loads(manifest_bytes.decode('utf-8'))
                
                m3u8_url = manifest['urls'][0]
                self.logger.debug(f"M3U8 URL: {m3u8_url}")
                
                session = self._get_session()
                async with session.get(m3u8_url, ssl=None) as response:
                    m3u8_content = await response.text()
                
                stream_urls = []
                current_resolution = None
                current_codec = None
                current_url = None
                
                for line in m3u8_content.split('\n'):
                    if "RESOLUTION=" in line and "CODECS=" in line:
                        resolution_match = re.search(r'RESOLUTION=(\d+x\d+)', line)
                        codec_match = re.search(r'CODECS="([^"]+)"', line)
                        
                        if resolution_match and codec_match:
                            current_resolution = resolution_match.group(1)
                            current_codec = codec_match.group(1)
                    elif line.startswith('http'):
                        current_url = line.strip()
                        
                        if current_resolution and current_codec and current_url:
                            stream_url = VideoStreamUrl(
                                videoid=video_id,
                                resolution=current_resolution,
                                resolutions=current_resolution.split('x'),
                                codec=current_codec,
                                m3u8Url=current_url
                            )
                            stream_urls.append(stream_url)
                            
                            current_resolution = None
                            current_codec = None
                            current_url = None
                
                if not stream_urls:
                    raise APIError(f"No stream URLs found in M3U8 for video {video_id}")
                
                stream_urls.sort(key=lambda x: int(x.resolutions[1]) if len(x.resolutions) > 1 else 0, reverse=True)
                
                requested_height = None
                if quality == VideoQuality.P360:
                    requested_height = 360
                elif quality == VideoQuality.P480:
                    requested_height = 480
                elif quality == VideoQuality.P720:
                    requested_height = 720
                elif quality == VideoQuality.P1080:
                    requested_height = 1080
                
                if quality == VideoQuality.MAX or requested_height is None:
                    self.logger.debug(f"Returning highest resolution: {stream_urls[0].resolution}")
                    return stream_urls[0]
                
                for url in stream_urls:
                    if len(url.resolutions) > 1 and int(url.resolutions[1]) <= requested_height:
                        self.logger.debug(f"Found matching resolution: {url.resolution}")
                        return url
                
                self.logger.debug(f"No matching resolution found, returning lowest: {stream_urls[-1].resolution}")
                return stream_urls[-1]
            else:
                self.logger.error(f"Unsupported manifest type for video: {manifest_type}")
                raise APIError(f"Unsupported manifest type for video: {manifest_type}")
                
        except Exception as e:
            self.logger.error(f"Error getting video stream URL: {str(e)}")
            raise APIError(f"Failed to get stream URL for video {video_id}: {str(e)}")
