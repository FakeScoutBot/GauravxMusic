#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

from pydantic import BaseModel


class CachedTrack(BaseModel):
    url: str
    name: str
    artist: str
    loop: int
    user: str
    file_path: str
    thumbnail: str
    track_id: str
    duration: int = 0
    platform: str


class TrackInfo(BaseModel):
    url: str
    cdnurl: str
    key: str
    name: str
    artist: str
    album: str
    tc: str
    cover: str
    lyrics: str
    duration: int
    year: int


class MusicTrack(BaseModel):
    url: str
    name: str
    artist: str
    id: str
    year: int
    cover: str
    duration: int
    platform: str


class PlatformTracks(BaseModel):
    tracks: list[MusicTrack]
