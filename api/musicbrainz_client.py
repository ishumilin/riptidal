"""
MusicBrainz API client for RIPTIDAL.

This module provides a client for interacting with the MusicBrainz API
to identify tracks from metadata.
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import quote

import aiohttp
from pydantic import BaseModel, Field

from riptidal.utils.logger import get_logger


class MusicBrainzRecording(BaseModel):
    """Model for a MusicBrainz recording."""
    id: str
    title: str
    length: Optional[int] = None  # Duration in milliseconds
    artist_credit: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    releases: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    isrcs: Optional[List[str]] = Field(default_factory=list)
    score: Optional[int] = None  # Search relevance score
    
    @property
    def artist_names(self) -> str:
        """Get comma-separated artist names."""
        if not self.artist_credit:
            return "Unknown Artist"
        
        names = []
        for credit in self.artist_credit:
            if isinstance(credit, dict):
                # Try different ways to extract artist name
                if 'name' in credit:
                    names.append(credit['name'])
                elif 'artist' in credit and isinstance(credit['artist'], dict):
                    if 'name' in credit['artist']:
                        names.append(credit['artist']['name'])
                # Also check for joinphrase which might contain additional artists
                if 'joinphrase' in credit and credit['joinphrase'].strip():
                    # Don't add the joinphrase itself, it's just a separator
                    pass
        
        # Debug log the extracted names
        if not names:
            get_logger(__name__).warning(f"Could not extract artist names from artist_credit: {self.artist_credit}")
            
        return ", ".join(names) if names else "Unknown Artist"
    
    @property
    def first_release_title(self) -> Optional[str]:
        """Get the title of the first release."""
        if self.releases and len(self.releases) > 0:
            return self.releases[0].get('title')
        return None


class MusicBrainzClient:
    """
    Client for interacting with the MusicBrainz API.
    
    This class provides methods for searching and identifying tracks
    using the MusicBrainz database.
    """
    
    def __init__(self, user_agent: str = "RIPTIDAL/0.1.99 (https://github.com/riptidal)"):
        """
        Initialize the MusicBrainz client.
        
        Args:
            user_agent: User agent string for API requests
        """
        self.base_url = "https://musicbrainz.org/ws/2"
        self.user_agent = user_agent
        self.logger = get_logger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0
        self._rate_limit_delay = 1.0  # 1 second between requests
    
    async def __aenter__(self):
        """Context manager entry."""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": self.user_agent}
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.session:
            await self.session.close()
            self.session = None
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get the current session or create a new one."""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": self.user_agent}
            )
        return self.session
    
    async def _ensure_rate_limit(self):
        """Ensure we don't exceed the rate limit."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self._rate_limit_delay:
            wait_time = self._rate_limit_delay - time_since_last
            self.logger.debug(f"Rate limiting: waiting {wait_time:.2f} seconds")
            await asyncio.sleep(wait_time)
        
        self._last_request_time = time.time()
    
    async def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a request to the MusicBrainz API.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            Response data as a dictionary
        """
        await self._ensure_rate_limit()
        
        url = f"{self.base_url}/{endpoint}"
        
        if params is None:
            params = {}
        
        # Always request JSON format
        params['fmt'] = 'json'
        
        self.logger.debug(f"MusicBrainz API request: GET {url} with params: {params}")
        
        try:
            session = self._get_session()
            async with session.get(url, params=params) as response:
                if response.status == 503:
                    # Rate limited, wait and retry
                    retry_after = response.headers.get('Retry-After', '10')
                    wait_time = int(retry_after)
                    self.logger.warning(f"Rate limited by MusicBrainz, waiting {wait_time} seconds")
                    await asyncio.sleep(wait_time)
                    return await self._request(endpoint, params)
                
                response.raise_for_status()
                data = await response.json()
                self.logger.debug(f"MusicBrainz API response: {response.status}")
                return data
                
        except aiohttp.ClientError as e:
            self.logger.error(f"MusicBrainz API error: {str(e)}")
            raise
    
    async def search_recordings(
        self,
        artist: Optional[str] = None,
        title: Optional[str] = None,
        album: Optional[str] = None,
        duration: Optional[int] = None,
        isrc: Optional[str] = None,
        limit: int = 10
    ) -> List[MusicBrainzRecording]:
        """
        Search for recordings in MusicBrainz.
        
        Args:
            artist: Artist name
            title: Track title
            album: Album name
            duration: Track duration in milliseconds
            isrc: ISRC code
            limit: Maximum number of results
            
        Returns:
            List of MusicBrainzRecording objects
        """
        query_parts = []
        
        if artist:
            query_parts.append(f'artist:"{artist}"')
        
        if title:
            query_parts.append(f'recording:"{title}"')
        
        if album:
            query_parts.append(f'release:"{album}"')
        
        if duration:
            # Convert to seconds and allow 5 second tolerance
            duration_sec = duration // 1000
            dur_min = duration_sec - 5
            dur_max = duration_sec + 5
            query_parts.append(f'dur:[{dur_min}000 TO {dur_max}000]')
        
        if isrc:
            query_parts.append(f'isrc:{isrc}')
        
        if not query_parts:
            raise ValueError("At least one search parameter must be provided")
        
        query = " AND ".join(query_parts)
        
        self.logger.info(f"Searching MusicBrainz with query: {query}")
        
        params = {
            'query': query,
            'limit': limit
        }
        
        data = await self._request('recording', params)
        
        recordings = []
        for recording_data in data.get('recordings', []):
            try:
                recording = MusicBrainzRecording(**recording_data)
                recordings.append(recording)
            except Exception as e:
                self.logger.error(f"Error parsing recording: {str(e)}")
                continue
        
        self.logger.info(f"Found {len(recordings)} recordings in MusicBrainz")
        return recordings
    
    async def lookup_recording_by_isrc(self, isrc: str) -> List[MusicBrainzRecording]:
        """
        Look up recordings by ISRC.
        
        Args:
            isrc: ISRC code
            
        Returns:
            List of MusicBrainzRecording objects
        """
        self.logger.info(f"Looking up recording by ISRC: {isrc}")
        
        data = await self._request(f'isrc/{isrc}')
        
        recordings = []
        for recording_data in data.get('recordings', []):
            try:
                recording = MusicBrainzRecording(**recording_data)
                recordings.append(recording)
            except Exception as e:
                self.logger.error(f"Error parsing recording: {str(e)}")
                continue
        
        return recordings
    
    def calculate_match_score(
        self,
        recording: MusicBrainzRecording,
        artist: Optional[str] = None,
        title: Optional[str] = None,
        album: Optional[str] = None,
        duration: Optional[int] = None
    ) -> float:
        """
        Calculate a match score for a recording against provided metadata.
        
        Args:
            recording: MusicBrainzRecording to score
            artist: Expected artist name
            title: Expected track title
            album: Expected album name
            duration: Expected duration in milliseconds
            
        Returns:
            Score between 0 and 1
        """
        score = 0.0
        total_weight = 0.0
        
        # Artist match (weight: 0.3)
        if artist and recording.artist_names:
            artist_lower = artist.lower()
            recording_artist_lower = recording.artist_names.lower()
            
            if artist_lower == recording_artist_lower:
                score += 0.3
            elif artist_lower in recording_artist_lower or recording_artist_lower in artist_lower:
                score += 0.2
            
            total_weight += 0.3
        
        # Title match (weight: 0.3)
        if title and recording.title:
            title_lower = title.lower()
            recording_title_lower = recording.title.lower()
            
            if title_lower == recording_title_lower:
                score += 0.3
            elif title_lower in recording_title_lower or recording_title_lower in title_lower:
                score += 0.2
            
            total_weight += 0.3
        
        # Album match (weight: 0.2)
        if album and recording.first_release_title:
            album_lower = album.lower()
            release_title_lower = recording.first_release_title.lower()
            
            if album_lower == release_title_lower:
                score += 0.2
            elif album_lower in release_title_lower or release_title_lower in album_lower:
                score += 0.1
            
            total_weight += 0.2
        
        # Duration match (weight: 0.2)
        if duration and recording.length:
            # Allow 5 second tolerance
            diff = abs(duration - recording.length)
            if diff <= 5000:  # Within 5 seconds
                score += 0.2
            elif diff <= 10000:  # Within 10 seconds
                score += 0.1
            
            total_weight += 0.2
        
        # Normalize score
        if total_weight > 0:
            return score / total_weight
        
        return 0.0
