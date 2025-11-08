# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Backend**: Automatic API key fallback during device login when the current client is invalid (401 invalid_client).

### Changed
- **Backend**: Packaging configuration corrected (console script to `riptidal.main:main_cli`, package discovery updated to include `riptidal.*`).
- **Backend**: Version alignment to `1.0.0` across runtime and distribution metadata.
- **Backend**: `main.py` now imports `__version__` from the package instead of hardcoding.

### Fixed
- **Backend**: Resolved “Cannot combine AUTHORIZATION header with AUTH argument” by avoiding Bearer token on OAuth endpoints or when using BasicAuth.
- **Backend**: Added missing dependency `requests` to project dependencies to support API key updates.

## [1.0.0] - 2025-01-09

### Added
- Asynchronous API client for efficient communication with Tidal
- OAuth2 device code flow authentication for secure login
- Download tracks in various qualities (up to MASTER)
- Download videos in various resolutions (up to 1080p)
- Multiple API key support with automatic updates from GitHub
- Track management with duplicate detection
- Full album downloading for favorite tracks
- Album download resumption for interrupted downloads
- Download favorite albums directly from the main menu
- Download all albums from favorite artists with option to include EPs and singles
- Download playlists with full album support
- Command-line interface with simplified menu
- Configurable settings with Pydantic
- Portable application design - all settings and data stored in project directory
- Comprehensive test suite
- Library index for efficient download tracking
- Skip downloads for items already in library index

### Changed
- Concurrent downloads fixed at 1 for stability

### Security
- Added comprehensive legal warnings and disclaimers
- Privacy protection with proper .gitignore configuration
