#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

import asyncio
import os
import random
import subprocess
from pathlib import Path
from typing import Optional

import aiofiles
from Crypto.Cipher import AES
from Crypto.Util import Counter
from yt_dlp import YoutubeDL, utils

from config import DOWNLOADS_DIR, PROXY_URL
from src.logger import LOGGER
from ._httpx import HttpxClient
from .dataclass import TrackInfo


async def get_cookie_file():
    cookie_dir = "cookies"
    try:
        if not os.path.exists(cookie_dir):
            LOGGER.warning(f"Cookie directory '{cookie_dir}' does not exist.")
            return None

        files = await asyncio.to_thread(os.listdir, cookie_dir)
        cookies_files = [f for f in files if f.endswith(".txt")]

        if not cookies_files:
            LOGGER.warning(f"No cookie files found in '{cookie_dir}'.")
            return None

        random_file = random.choice(cookies_files)
        return os.path.join(cookie_dir, random_file)
    except Exception as e:
        LOGGER.warning(f"Error accessing cookie directory: {e}")
        return None


class YouTubeDownload:
    def __init__(self, track: TrackInfo):
        """
        Initialize the YouTubeDownload class with a video ID.
        """
        self.track = track
        self.video_id = track.tc
        self.video_url = f"https://www.youtube.com/watch?v={self.video_id}"
        self.output_file = Path(DOWNLOADS_DIR) / f"{track.tc}.mp3"

    async def process(self) -> Optional[str]:
        """Download the audio from YouTube and return the path to the downloaded file."""
        if self.output_file.exists():
            LOGGER.info(f"✅ Found existing file: {self.output_file}")
            return str(self.output_file)
        return await self._download_with_yt_dlp()

    async def _download_with_yt_dlp(self) -> Optional[str]:
        """Download audio using yt-dlp with proxy support."""
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": str(self.output_file.with_suffix("")),
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
        }

        if cookie_file := await get_cookie_file():
            ydl_opts["cookiefile"] = cookie_file

        # Add proxy if configured
        if PROXY_URL:
            ydl_opts["proxy"] = PROXY_URL

        try:
            loop = asyncio.get_running_loop()
            with YoutubeDL(ydl_opts) as ydl:
                await loop.run_in_executor(None, ydl.download, [self.video_url])
            LOGGER.info(f"✅ Downloaded: {self.output_file}")
            return str(self.output_file)
        except utils.DownloadError as e:
            LOGGER.error(f"❌ Download error for {self.video_url}: {e}")
            return None
        except Exception as e:
            LOGGER.error(
                f"❌ Unexpected error downloading {self.video_url}: {e}", exc_info=True
            )
            return None


async def rebuild_ogg(filename: str) -> None:
    """Fixes broken OGG headers."""
    if not os.path.exists(filename):
        LOGGER.error(f"❌ Error: {filename} not found.")
        return

    try:
        async with aiofiles.open(filename, "r+b") as ogg_file:
            ogg_s = b"OggS"
            zeroes = b"\x00" * 10
            vorbis_start = b"\x01\x1e\x01vorbis"
            channels = b"\x02"
            sample_rate = b"\x44\xac\x00\x00"
            bit_rate = b"\x00\xe2\x04\x00"
            packet_sizes = b"\xb8\x01"

            await ogg_file.seek(0)
            await ogg_file.write(ogg_s)
            await ogg_file.seek(6)
            await ogg_file.write(zeroes)
            await ogg_file.seek(26)
            await ogg_file.write(vorbis_start)
            await ogg_file.seek(39)
            await ogg_file.write(channels)
            await ogg_file.seek(40)
            await ogg_file.write(sample_rate)
            await ogg_file.seek(48)
            await ogg_file.write(bit_rate)
            await ogg_file.seek(56)
            await ogg_file.write(packet_sizes)
            await ogg_file.seek(58)
            await ogg_file.write(ogg_s)
            await ogg_file.seek(62)
            await ogg_file.write(zeroes)
    except Exception as e:
        LOGGER.error(f"Error rebuilding OGG file {filename}: {e}")


class SpotifyDownload:
    def __init__(self, track: TrackInfo):
        self.track = track
        self.client = HttpxClient()
        self.encrypted_file = os.path.join(DOWNLOADS_DIR, f"{track.tc}.encrypted.ogg")
        self.decrypted_file = os.path.join(DOWNLOADS_DIR, f"{track.tc}.decrypted.ogg")
        self.output_file = os.path.join(DOWNLOADS_DIR, f"{track.tc}.ogg")

    async def decrypt_audio(self) -> None:
        """Decrypt the downloaded audio file using a stream-based approach."""
        try:
            key = bytes.fromhex(self.track.key)
            iv = bytes.fromhex("72e067fbddcbcf77ebe8bc643f630d93")
            iv_int = int.from_bytes(iv, "big")
            cipher = AES.new(
                key, AES.MODE_CTR, counter=Counter.new(128, initial_value=iv_int)
            )

            chunk_size = 8192  # 8KB chunks
            async with aiofiles.open(self.encrypted_file, "rb") as fin, aiofiles.open(
                    self.decrypted_file, "wb"
            ) as fout:
                while chunk := await fin.read(chunk_size):
                    decrypted_chunk = cipher.decrypt(chunk)
                    await fout.write(decrypted_chunk)
        except Exception as e:
            LOGGER.error(f"Error decrypting audio file: {e}")
            raise

    async def fix_audio(self) -> None:
        """Fix the decrypted audio file using FFmpeg."""
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-i",
                self.decrypted_file,
                "-c",
                "copy",
                self.output_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                LOGGER.error(f"FFmpeg error: {stderr.decode().strip()}")
                raise subprocess.CalledProcessError(process.returncode, "ffmpeg")
        except Exception as e:
            LOGGER.error(f"Error fixing audio file: {e}")
            raise

    async def _cleanup(self) -> None:
        """Cleanup temporary files asynchronously."""
        for file in [self.encrypted_file, self.decrypted_file]:
            try:
                if os.path.exists(file):
                    os.remove(file)
            except Exception as e:
                LOGGER.warning(f"Error removing {file}: {e}")

    async def process(self) -> Optional[str]:
        """Main function to download, decrypt, and fix audio."""
        if os.path.exists(self.output_file):
            LOGGER.info(f"✅ Found existing file: {self.output_file}")
            return self.output_file

        _track_id = self.track.tc
        if not self.track.cdnurl or not self.track.key:
            LOGGER.warning(f"Missing CDN URL or key for track: {_track_id}")
            return None

        try:
            await self.client.download_file(self.track.cdnurl, self.encrypted_file)
            await self.decrypt_audio()
            await rebuild_ogg(self.decrypted_file)
            await self.fix_audio()
            await self._cleanup()
            LOGGER.info(f"✅ Successfully processed track: {self.output_file}")
            return self.output_file
        except Exception as e:
            LOGGER.error(f"Error processing track {_track_id}: {e}")
            await self._cleanup()
            return None
