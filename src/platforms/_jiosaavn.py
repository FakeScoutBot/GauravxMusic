#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

import asyncio
import os
import re
from typing import Optional, Any

import yt_dlp

import config
from src.logger import LOGGER
from ._httpx import HttpxClient
from .dataclass import PlatformTracks, TrackInfo, MusicTrack
from .downloader import MusicService


class JiosaavnData(MusicService):
    JIOSAAVN_SONG_PATTERN = re.compile(
        r"^(https?://)?(www\.)?jiosaavn\.com/song/[\w-]+/[a-zA-Z0-9_-]+",
        re.IGNORECASE,
    )

    JIOSAAVN_PLAYLIST_PATTERN = re.compile(
        r"^(https?://)?(www\.)?jiosaavn\.com/featured/[\w-]+/[a-zA-Z0-9_-]+$",
        re.IGNORECASE,
    )

    def __init__(self, query: str = None) -> None:
        self.query = query
        self.client = HttpxClient()
        self._ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
        }

    def is_valid(self, url: str) -> bool:
        """Check if the URL is a valid JioSaavn song or playlist URL."""
        if not url:
            return False
        return bool(self.JIOSAAVN_SONG_PATTERN.match(url)) or bool(
            self.JIOSAAVN_PLAYLIST_PATTERN.match(url)
        )

    async def _fetch_data(self, url: str) -> Optional[dict[str, Any]]:
        """Fetch data based on URL type (song or playlist)."""
        try:
            if self.JIOSAAVN_SONG_PATTERN.match(url):
                return await self.get_track_data(url)
            elif self.JIOSAAVN_PLAYLIST_PATTERN.match(url):
                return await self.get_playlist_data(url)
            return await self.search()
        except Exception as e:
            LOGGER.error(f"Error fetching data from {url}: {str(e)}")
            return None

    async def search(self) -> Optional[PlatformTracks]:
        """Search for tracks. Falls back to YouTube if not a JioSaavn URL."""
        if not self.query:
            return None

        if self.is_valid(self.query):
            data = await self._fetch_data(self.query)
        else:
            try:
                _url = f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&query={self.query}&_format=json&_marker=0&ctx=wap6dot0"
                _data = await self.client.make_request(_url)

                data = (
                    {
                        "results": [
                            self._format_track(video) for video in _data.get("songs", {}).get("data", [])
                        ]
                    }
                    if "songs" in _data and "data" in _data["songs"]
                    else None
                )
            except Exception as e:
                LOGGER.error(f"Error searching: {e}")
                data = None

        return self._create_platform_tracks(data) if data else None

    async def get_recommendations(self) -> Optional[PlatformTracks]:
        """Placeholder for recommendations functionality."""
        return None

    async def get_info(self) -> Optional[PlatformTracks]:
        """Get track or playlist info."""
        if not self.is_valid(self.query):
            return None

        data = await self._fetch_data(self.query)
        return self._create_platform_tracks(data) if data else None

    async def get_track(self) -> Optional[TrackInfo]:
        """Get detailed track information."""
        if not self.query:
            return None

        url = self.format_jiosaavn_url(self.query)
        data = await self.get_track_data(url)

        if not data or not data.get("results"):
            return None

        track_data = data["results"][0]
        return TrackInfo(
            cdnurl=track_data.get("cdnurl", ""),
            key="nil",
            name=track_data.get("name", ""),
            artist=track_data.get("artist", "Unknown"),
            tc=track_data.get("id", ""),
            album=track_data.get("album", ""),
            cover=track_data.get("cover", ""),
            lyrics="None",
            duration=track_data.get("duration", 0),
            year=track_data.get("year", 0),
        )

    @staticmethod
    def format_jiosaavn_url(name_and_id: str) -> str:
        """Format a JioSaavn URL from name and ID."""
        if not name_and_id:
            return ""

        title, song_id = name_and_id.rsplit("/", 1)
        title = title.lower()
        title = re.sub(r'[\(\)"\',]', "", title)
        title = title.replace(" ", "-")
        return f"https://www.jiosaavn.com/song/{title}/{song_id}"

    async def get_track_data(self, url: str) -> Optional[dict[str, Any]]:
        """Get track data using yt-dlp."""
        try:
            with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                return {"results": [self._format_track(info)]} if info else None
        except Exception as e:
            LOGGER.error(f"Error getting track data from {url}: {str(e)}")
            return None

    async def get_playlist_data(self, url: str) -> Optional[dict[str, Any]]:
        """Get playlist data using yt-dlp."""
        try:
            with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)

                if not info or "entries" not in info:
                    LOGGER.error(f"No entries found in playlist: {url}")
                    return None

                playlist_tracks = [
                    self._format_track(track) for track in info["entries"] if track
                ]
                return {"results": playlist_tracks}
        except Exception as e:
            LOGGER.error(f"Error getting playlist data from {url}: {str(e)}")
            return None

    async def download_track(self, track: TrackInfo) -> Optional[str]:
        """Download a track to local storage."""
        if not track or not track.cdnurl:
            return None

        dl_file = os.path.join(config.DOWNLOADS_DIR, f"{track.tc}.m4a")
        try:
            return await self.client.download_file(track.cdnurl, dl_file)
        except Exception as e:
            LOGGER.error(f"Error downloading track {track.tc}: {str(e)}")
            return None

    @staticmethod
    def _format_track(track_data: dict[str, Any]) -> dict[str, Any]:
        """Format track data into a standardized format."""
        if not track_data:
            return {}

        formats = track_data.get("formats", [])
        best_format = max(formats, key=lambda x: x.get("abr", 0), default={})
        download_url = best_format.get("url", "")
        artists = track_data.get("artists", [])
        artist = track_data.get("artist", artists[0] if artists else "")
        _title = track_data.get("title", "")
        _display_id = f"{_title}/" + track_data.get("url", "").split("/")[-1]

        return {
            "id": track_data.get("display_id", _display_id),
            "tc": track_data.get("display_id", _display_id),
            "name": _title,
            "album": track_data.get("album", ""),
            "duration": track_data.get("duration", 0),
            "artist": artist,
            "cover": track_data.get("thumbnail", ""),
            "year": track_data.get("release_year", 0),
            "platform": "jiosaavn",
            "cdnurl": track_data.get("url", download_url),
        }

    @staticmethod
    def _create_platform_tracks(data: dict) -> Optional[PlatformTracks]:
        """Create PlatformTracks object from formatted data."""
        if not data or "results" not in data or not data["results"]:
            return None

        return PlatformTracks(
            tracks=[MusicTrack(**track) for track in data["results"] if track]
        )
