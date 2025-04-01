#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

import asyncio
from typing import Optional, Any

import aiofiles
import httpx

import config
from config import API_KEY
from src.logger import LOGGER


class HttpxClient:
    def __init__(
        self, timeout: int = 10, download_timeout: int = 60, max_redirects: int = 2
    ):
        """
        Initialize the HTTP client with configurable timeouts and redirect settings.

        :param timeout: Timeout for general HTTP requests in seconds.
        :param download_timeout: Timeout for file downloads in seconds.
        :param max_redirects: Maximum number of redirects to follow.
        """
        self.download_timeout = download_timeout
        self.session = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=max_redirects,
        )

    async def close(self):
        """Close the HTTP session."""
        await self.session.aclose()

    async def download_file(self, url: str, filename: str) -> str | None:
        """
        Download a file asynchronously and save it to disk, following redirects if needed.

        :param url: The URL of the file to download.
        :param filename: The path where the file will be saved.
        :return: The filename if successful, otherwise None.
        """
        if not url:
            LOGGER.warning("URL is empty")
            return None

        try:
            async with self.session.stream(
                "GET", url, timeout=self.download_timeout
            ) as response:
                response.raise_for_status()
                async with aiofiles.open(filename, "wb") as f:
                    async for chunk in response.aiter_bytes(8192):
                        await f.write(chunk)

                LOGGER.info(f"Downloaded file: {filename}")
                return filename

        except httpx.TooManyRedirects as e:
            LOGGER.error(f"Too many redirects while downloading {url}: {e}")
        except httpx.HTTPStatusError as e:
            LOGGER.error(
                f"HTTP error while downloading {url}: {e.response.status_code}"
            )
        except httpx.RequestError as e:
            LOGGER.error(f"Request failed while downloading {url}: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error while downloading {url}: {e}")

        return None

    async def make_request(
        self, url: str, max_retries: int = 3, backoff_factor: float = 1.0
    ) -> Optional[dict[str, Any]]:
        """
        Make an HTTP GET request with retries and exponential backoff, following redirects if needed.

        :param url: The URL to request.
        :param max_retries: Maximum number of retries.
        :param backoff_factor: Factor for exponential backoff.
        :return: The JSON response as a dictionary if successful, otherwise None.
        """
        if not url:
            LOGGER.warning("URL is empty")
            return None

        headers = None
        if config.API_URL and url.startswith(config.API_URL):
            headers = {"X-API-Key": API_KEY}

        for attempt in range(max_retries):
            try:
                response = await self.session.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.TooManyRedirects as e:
                LOGGER.error(f"Too many redirects for {url}: {e}")
                if attempt == max_retries - 1:
                    return None
            except httpx.HTTPStatusError as e:
                LOGGER.error(f"HTTP error for {url}: {e.response.status_code}")
                if attempt == max_retries - 1:
                    return None
            except httpx.RequestError as e:
                LOGGER.error(f"Request failed for {url}: {e}")
                if attempt == max_retries - 1:
                    return None
            except Exception as e:
                LOGGER.error(f"Unexpected error for {url}: {e}")
                return None

            await asyncio.sleep(backoff_factor * (2**attempt))

        return None
