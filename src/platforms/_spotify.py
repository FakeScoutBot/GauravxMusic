#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

import re
from typing import Optional

import config
from src.logger import LOGGER
from ._httpx import HttpxClient
from ._dl_helper import SpotifyDownload
from .dataclass import PlatformTracks, TrackInfo, MusicTrack
from .downloader import MusicService


class SpotifyData(MusicService):
    SPOTIFY_URL_PATTERN = re.compile(
        r"^(https?://)?(open\.spotify\.com/(track|playlist|album|artist)/[a-zA-Z0-9]+)(\?.*)?$"
    )

    API_URL = config.API_URL
    def __init__(self, query: str = None) -> None:
        self.query = query
        self.client = HttpxClient()

    def is_valid(self, url: str) -> bool:
        return bool(self.SPOTIFY_URL_PATTERN.match(url)) if url else False

    async def get_recommendations(self) -> Optional[PlatformTracks]:
        url = f"{self.API_URL}/recommend_songs?lim=4"
        data = await self.client.make_request(url)
        return self._create_platform_tracks(data) if data else None

    async def get_info(self) -> Optional[PlatformTracks]:
        if not self.is_valid(self.query):
            return None
        data = await self.client.make_request(
            f"{self.API_URL}/get_url_new?url={self.query}"
        )
        return self._create_platform_tracks(data) if data else None

    async def search(self) -> Optional[PlatformTracks]:
        url = f"{self.API_URL}/search_track/{self.query}"
        data = await self.client.make_request(url)
        return self._create_platform_tracks(data) if data else None

    async def get_track(self) -> Optional[TrackInfo]:
        url = f"{self.API_URL}/get_track?id={self.query}"
        data = await self.client.make_request(url)
        return TrackInfo(**data) if data else None

    async def download_track(self, track: TrackInfo) -> Optional[str]:
        try:
            return await SpotifyDownload(track).process()
        except Exception as e:
            LOGGER.error(f"Error downloading track: {e}")
            return None

    @staticmethod
    def _create_platform_tracks(data: dict) -> Optional[PlatformTracks]:
        if data and "results" in data:
            return PlatformTracks(
                tracks=[MusicTrack(**track) for track in data["results"]]
            )
        return None
