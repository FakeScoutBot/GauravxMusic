#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

import re
from typing import Optional, Any

from py_yt import VideosSearch, Playlist

from src.logger import LOGGER
from ._dl_helper import YouTubeDownload
from ._httpx import HttpxClient
from .dataclass import PlatformTracks, TrackInfo, MusicTrack
from .downloader import MusicService


class YouTubeData(MusicService):
    YOUTUBE_VIDEO_PATTERN = re.compile(
        r"^(?:https?://)?(?:www\.)?(?:youtube\.com|music\.youtube\.com|youtu\.be)/(?:watch\?v=|embed/|v/)?([\w-]+)",
        re.IGNORECASE,
    )
    YOUTUBE_PLAYLIST_PATTERN = re.compile(
        r"^(?:https?://)?(?:www\.)?(?:youtube\.com|music\.youtube\.com)/playlist\?[^#]*\blist=([\w-]+)",
        re.IGNORECASE,
    )

    def __init__(self, query: str = None) -> None:
        self.client = HttpxClient()
        self.query = None if not query else query.split("&")[0] if query and "&" in query else query

    def is_valid(self, url: str) -> bool:
        if not url:
            return False
        return bool(self.YOUTUBE_VIDEO_PATTERN.match(url) or self.YOUTUBE_PLAYLIST_PATTERN.match(url))

    async def _fetch_data(self, url: str) -> Optional[dict[str, Any]]:
        if self.YOUTUBE_PLAYLIST_PATTERN.match(url):
            LOGGER.info(f"Fetching data for YouTube playlist: {url}")
            return await self._get_playlist(url)
        return await self._get_youtube_url(url)

    async def get_info(self) -> Optional[PlatformTracks]:
        if not self.is_valid(self.query):
            return None

        data = await self._fetch_data(self.query)
        return self._create_platform_tracks(data) if data else None

    async def search(self) -> Optional[PlatformTracks]:
        if not self.query:
            return None
        if self.is_valid(self.query):
            return await self.get_info()
        try:
            search = VideosSearch(self.query, limit=5)
            results = await search.next()
            data = {"results": [self._format_track(video) for video in results["result"]]} if "result" in results else None
        except Exception as e:
            LOGGER.error(f"Error searching: {e}")
            data = None

        return self._create_platform_tracks(data) if data else None

    async def get_track(self) -> Optional[TrackInfo]:
        url = f"https://youtube.com/watch?v={self.query}"
        try:
            data = await self._get_youtube_url(url)
            if not data or "results" not in data:
                return None
            track_data = data["results"][0]
            return TrackInfo(
                cdnurl="None",
                key="None",
                name=track_data["name"],
                artist=track_data["artist"],
                tc=track_data["id"],
                album="YouTube",
                cover=track_data["cover"],
                lyrics="None",
                duration=track_data["duration"],
                url=f"https://youtube.com/watch?v={track_data['id']}",
                year=0,
            )
        except Exception as e:
            LOGGER.error(f"Error fetching track: {e}")
            return None

    async def download_track(self, track: TrackInfo) -> Optional[str]:
        try:
            return await YouTubeDownload(track).process()
        except Exception as e:
            LOGGER.error(f"Error downloading track: {e}")
            return None

    async def _get_youtube_url(self, url: str) -> Optional[dict[str, Any]]:
        normalized_url = await self._normalize_youtube_url(url)
        if not normalized_url:
            return None
        data = await self._fetch_oembed_data(normalized_url)
        if data:
            video_id = normalized_url.split("v=")[1]
            return {
                "results": [{
                    "id": video_id,
                    "name": data.get("title"),
                    "duration": 0,
                    "artist": data.get("author_name", ""),
                    "cover": data.get("thumbnail_url", ""),
                    "year": 0,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "platform": "youtube",
                }]
            }
        return await self._fallback_search_youtube(normalized_url)

    async def _fallback_search_youtube(self, url: str) -> Optional[dict[str, Any]]:
        try:
            search = VideosSearch(url, limit=1)
            results = await search.next()
        except Exception as e:
            LOGGER.error(f"Error searching: {e}")
            return None
        return {"results": [self._format_track(video) for video in results["result"]]} if "result" in results else None

    @staticmethod
    async def _get_playlist(url: str) -> Optional[dict[str, Any]]:
        try:
            playlist = await Playlist.getVideos(url)
            return {"results": [YouTubeData._format_track(track) for track in playlist.get("videos", [])]} if playlist else None
        except Exception as e:
            LOGGER.error(f"Error getting playlist: {e}")
            return None

    async def get_recommendations(self) -> Optional[PlatformTracks]:
        return None

    @staticmethod
    def _duration_to_seconds(duration: str) -> int:
        if not duration:
            return 0
        parts = duration.split(":")
        if len(parts) == 3:  # Format: H:MM:SS
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:  # Format: MM:SS
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        else:
            return 0

    async def _fetch_oembed_data(self, url: str) -> Optional[dict[str, Any]]:
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        return await self.client.make_request(oembed_url)

    @staticmethod
    async def _normalize_youtube_url(url: str) -> Optional[str]:
        if "youtu.be" in url:
            parts = url.split("youtu.be/")
            if len(parts) < 2:
                return None
            path_part = parts[1]
            video_id = path_part.partition('?')[0].partition('#')[0]
            return f"https://www.youtube.com/watch?v={video_id}"
        return url

    @staticmethod
    def _create_platform_tracks(data: dict) -> Optional[PlatformTracks]:
        return PlatformTracks(tracks=[MusicTrack(**track) for track in data["results"]] if data and "results" in data else [])

    @staticmethod
    def _format_track(track_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": track_data.get("id"),
            "name": track_data.get("title"),
            "duration": YouTubeData._duration_to_seconds(track_data.get("duration", "0:00")),
            "artist": track_data.get("channel", {}).get("name", "Unknown"),
            "cover": track_data.get("thumbnails", [{}])[-1].get("url", ""),
            "year": 0,
            "url": f"https://www.youtube.com/watch?v={track_data.get('id')}",
            "platform": "youtube",
        }
