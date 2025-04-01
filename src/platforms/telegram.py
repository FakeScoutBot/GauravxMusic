#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

from typing import Union, Optional

from pytdbot import types


class Telegram:
    """A helper class to process Telegram messages containing playable media (audio/video)."""

    MAX_FILE_SIZE = 400 * 1024 * 1024  # 400MB

    def __init__(self, reply: Optional[types.Message]):
        """Initialize with a Telegram message object."""
        self.msg = reply

    def is_valid(self) -> bool:
        """Checks if the message contains a playable media file (audio or video) and is within size limits."""
        if not self.msg or isinstance(self.msg, types.Error):
            return False

        content = self.msg.content
        if isinstance(content, types.MessageVideo):
            file_size = content.video.video.size
        elif isinstance(content, types.MessageAudio):
            file_size = content.audio.audio.size
        else:
            return False

        return 0 < file_size <= self.MAX_FILE_SIZE

    def get_file_name(self) -> str:
        """Retrieves the file name from the media message."""
        if not self.is_valid():
            return "Unknown Media"

        content = self.msg.content
        if isinstance(content, types.MessageVideo):
            return getattr(content.video, "file_name", "Video.mp4")
        if isinstance(content, types.MessageAudio):
            return getattr(content.audio, "file_name", "Audio.mp3")

        return "Unknown Media"

    async def dl(self) -> Union[types.Error, types.LocalFile]:
        """Downloads the media file asynchronously if valid."""
        if not self.is_valid():
            return types.Error(
                message="Invalid file for download or exceeds size limit."
            )
        return await self.msg.download()
