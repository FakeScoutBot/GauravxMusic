#  Copyright (c) 2025 AshokShau.
#  TgMusicBot is an open-source Telegram music bot licensed under AGPL-3.0.
#  All rights reserved where applicable.
#
#

import asyncio
import os
import random
import re
from typing import Optional, Union

from pyrogram import Client as PyroClient, errors
from pytdbot import Client, types
from pytgcalls import PyTgCalls, exceptions
from pytgcalls.types import (
    MediaStream,
    Update,
    stream,
    VideoQuality,
    AudioQuality,
    ChatUpdate,
    UpdatedGroupCallParticipant,
)

import config
from src.database import db
from src.logger import LOGGER
from src.modules.utils import sec_to_min, get_audio_duration
from src.modules.utils.buttons import play_button, update_progress_bar
from src.modules.utils.cacher import chat_cache
from src.modules.utils.thumbnails import gen_thumb
from src.platforms import ApiData, YouTubeData, SpotifyData, JiosaavnData
from src.platforms.downloader import MusicServiceWrapper
from src.platforms.dataclass import CachedTrack


class CallError(Exception):
    """Custom exception for call-related errors."""

    def __init__(self, message: str):
        super().__init__(message)


class MusicBot:
    """Main music bot class handling voice chat operations."""

    def __init__(self):
        self.calls: dict[str, PyTgCalls] = {}
        self.client_counter: int = 1
        self.available_clients: list[str] = []
        self.bot: Optional[Client] = None

    async def add_bot(self, client: Client) -> None:
        """Add the main bot client."""
        self.bot = client

    async def _get_client_name(self, chat_id: int) -> str:
        """Get the associated client for a specific chat ID."""
        if chat_id == 1:  # Special case for random client selection
            if not self.available_clients:
                raise RuntimeError("No available clients!")
            return random.choice(self.available_clients)

        # For groups/channels
        assistant = await db.get_assistant(chat_id)
        if assistant and assistant in self.available_clients:
            return assistant

        if not self.available_clients:
            raise RuntimeError("No available clients to assign!")

        new_client = random.choice(self.available_clients)
        await db.set_assistant(chat_id, assistant=new_client)
        return new_client

    async def get_client(self, chat_id: int) -> Union[PyroClient, types.Error]:
        """Get the Pyrogram client for a specific chat ID."""
        try:
            client_name = await self._get_client_name(chat_id)
            ub = self.calls[client_name].mtproto_client

            if ub is None or not hasattr(ub, "me") or ub.me is None:
                return types.Error(code=400, message="Client not found or not ready")

            return ub
        except Exception as e:
            LOGGER.error(f"Error getting client for chat {chat_id}: {e}")
            return types.Error(code=500, message=str(e))

    async def start_client(
        self, api_id: int, api_hash: str, session_string: str
    ) -> None:
        """Start a new Pyrogram client and PyTgCalls instance."""
        client_name = f"client{self.client_counter}"
        try:
            user_bot = PyroClient(
                client_name,
                api_id=api_id,
                api_hash=api_hash,
                session_string=session_string,
            )
            calls = PyTgCalls(user_bot, cache_duration=100)
            self.calls[client_name] = calls
            self.available_clients.append(client_name)
            self.client_counter += 1

            await calls.start()
            LOGGER.info(f"Client {client_name} started successfully")
        except Exception as e:
            LOGGER.error(f"Error starting client {client_name}: {e}")
            raise

    async def register_decorators(self) -> None:
        """Register event handlers for all clients."""
        for call_instance in self.calls.values():

            @call_instance.on_update()
            async def general_handler(_, update: Update):
                try:
                    LOGGER.debug(f"Received update: {update}")
                    if isinstance(update, stream.StreamEnded):
                        await self.play_next(update.chat_id)
                    elif isinstance(update, UpdatedGroupCallParticipant):
                        return
                    elif isinstance(update, ChatUpdate) and (
                        update.status.KICKED or update.status.LEFT_GROUP
                    ):
                        await chat_cache.clear_chat(update.chat_id)
                except Exception as e:
                    LOGGER.error(f"Error in general handler: {e}")

    async def play_media(
        self,
        chat_id: int,
        file_path: str,
        video: bool = False,
        ffmpeg_parameters: Optional[str] = None,
    ) -> None:
        """Play media on a specific client."""
        LOGGER.info(f"Playing media for chat {chat_id}: {file_path}")
        try:
            _stream = MediaStream(
                audio_path=file_path,
                media_path=file_path,
                audio_parameters=AudioQuality.MEDIUM if video else AudioQuality.STUDIO,
                video_parameters=VideoQuality.FHD_1080p if video else VideoQuality.SD_360p,
                video_flags=(
                    MediaStream.Flags.AUTO_DETECT if video else MediaStream.Flags.IGNORE
                ),
                ffmpeg_parameters=ffmpeg_parameters,
            )

            client_name = await self._get_client_name(chat_id)
            await self.calls[client_name].play(chat_id, _stream)
        except (errors.ChatAdminRequired, exceptions.NoActiveGroupCall) as e:
            LOGGER.warning(f"Error playing media for chat {chat_id}: {e}")
            await chat_cache.clear_chat(chat_id)
            raise CallError(
                "No active group call \nPlease start a call and try again"
            ) from e
        except exceptions.UnMuteNeeded as e:
            LOGGER.warning(f"Error playing media for chat {chat_id}: {e}")
            raise CallError(
                "Needed to unmute the userbot first \nPlease unmute my assistant and try again"
            ) from e
        except Exception as e:
            LOGGER.error(f"Error playing media for chat {chat_id}: {e}", exc_info=True)
            raise CallError(f"Error playing media: {e}") from e

    async def play_next(self, chat_id: int) -> None:
        """Handle song queue logic."""
        LOGGER.info(f"Playing next song for chat {chat_id}")
        try:
            loop = await chat_cache.get_loop_count(chat_id)
            if loop > 0:
                await chat_cache.set_loop_count(chat_id, loop - 1)
                if current_song := await chat_cache.get_current_song(chat_id):
                    await self._play_song(chat_id, current_song)
                    return

            if next_song := await chat_cache.get_next_song(chat_id):
                await chat_cache.remove_current_song(chat_id)
                await self._play_song(chat_id, next_song)
            else:
                await self._handle_no_songs(chat_id)
        except Exception as e:
            LOGGER.error(f"Error in play_next for chat {chat_id}: {e}", exc_info=True)

    async def _play_song(self, chat_id: int, song: CachedTrack) -> None:
        """Download and play a song."""
        LOGGER.info(f"Playing song for chat {chat_id}")
        try:
            reply = await self.bot.sendTextMessage(chat_id, "⏹️ Loading... Please wait.")
            if isinstance(reply, types.Error):
                LOGGER.error(f"Error sending message: {reply}")
                return

            file_path = song.file_path or await self.song_download(song)
            if not file_path:
                await reply.edit_text("❌ Error downloading song. Playing next...")
                await self.play_next(chat_id)
                return

            await self.play_media(chat_id, file_path)

            duration = song.duration or await get_audio_duration(file_path)
            text = (
                f"<b>Now playing <a href='{song.thumbnail or 'https://t.me/FallenProjects'}'>:</a></b>\n\n"
                f"‣ <b>Title:</b> {song.name}\n"
                f"‣ <b>Duration:</b> {sec_to_min(duration)}\n"
                f"‣ <b>Requested by:</b> {song.user}"
            )

            thumbnail = await gen_thumb(song)
            parse = await self.bot.parseTextEntities(text, types.TextParseModeHTML())
            if isinstance(parse, types.Error):
                LOGGER.error(f"Parse error: {parse}")
                parse = parse.message

            input_content = types.InputMessagePhoto(
                photo=(
                    types.InputFileRemote(thumbnail)
                    if thumbnail.startswith("http")
                    else types.InputFileLocal(thumbnail)
                ),
                caption=parse,
            )

            reply = await self.bot.editMessageMedia(
                chat_id=chat_id,
                message_id=reply.id,
                input_message_content=input_content,
                reply_markup=play_button(0, duration),
            )

            if isinstance(reply, types.Error):
                LOGGER.warning(f"Error editing message: {reply}")
                return

            asyncio.create_task(update_progress_bar(self.bot, reply, 3, song.duration))
        except Exception as e:
            LOGGER.error(f"Error in _play_song for chat {chat_id}: {e}", exc_info=True)

    @staticmethod
    async def song_download(song: CachedTrack) -> Optional[str]:
        """Handle song downloading based on platform."""
        _track_id = song.track_id
        _url = song.url
        _platform = song.platform
        if _platform == "youtube":
            youtube = YouTubeData(_track_id)
            if track := await youtube.get_track():
                return await youtube.download_track(track)
        elif _platform == "spotify":
            spotify = SpotifyData(_track_id)
            if track := await spotify.get_track():
                return await spotify.download_track(track)
        elif _platform == "jiosaavn":
            jiosaavn = JiosaavnData(_url)
            if track := await jiosaavn.get_track():
                return await jiosaavn.download_track(track)
        elif _platform in ["apple_music", "soundcloud"]:
            _music = ApiData(_url)
            if track := await _music.get_track():
                return await _music.download_track(track)
        LOGGER.warning(f"Unknown platform: {_platform}")
        return None

    async def _handle_no_songs(self, chat_id: int) -> None:
        """Handle the case when there are no songs left in the queue."""
        try:
            await self.end(chat_id)

            if recommendations := await MusicServiceWrapper().get_recommendations():
                buttons = [
                    [
                        types.InlineKeyboardButton(
                            f"{track.name[:18]} - {track.artist}",
                            type=types.InlineKeyboardButtonTypeCallback(
                                f"play_{track.platform}_{track.id}".encode()
                            ),
                        )
                    ]
                    for track in recommendations.tracks
                ]

                reply = await self.bot.sendTextMessage(
                    chat_id,
                    text="No more songs in queue. Here are some recommendations:\n\n",
                    reply_markup=types.ReplyMarkupInlineKeyboard(buttons),
                )

                if isinstance(reply, types.Error):
                    LOGGER.warning(f"Error sending recommendations: {reply}")
                return

            reply = await self.bot.sendTextMessage(
                chat_id, text="No more songs in queue. Use /play to add some."
            )

            if isinstance(reply, types.Error):
                LOGGER.warning(f"Error sending empty queue message: {reply}")

        except Exception as e:
            LOGGER.error(
                f"Error in _handle_no_songs for chat {chat_id}: {e}", exc_info=True
            )

    async def end(self, chat_id: int) -> None:
        """End the current call."""
        LOGGER.info(f"Ending call for chat {chat_id}")
        try:
            await chat_cache.clear_chat(chat_id)
            client_name = await self._get_client_name(chat_id)
            await self.calls[client_name].leave_call(chat_id)
        except errors.GroupCallInvalid:
            pass
        except Exception as e:
            LOGGER.error(f"Error ending call for chat {chat_id}: {e}")

    async def seek_stream(
        self, chat_id: int, file_path_or_url: str, to_seek: int, duration: int
    ) -> None:
        """Seek to a specific position in the stream."""
        try:
            is_url = bool(re.match(r"http(s)?://", file_path_or_url))
            if is_url or not os.path.isfile(file_path_or_url):
                ffmpeg_params = f"-ss {to_seek} -i {file_path_or_url} -to {duration}"
            else:
                ffmpeg_params = f"-ss {to_seek} -to {duration}"

            await self.play_media(
                chat_id, file_path_or_url, ffmpeg_parameters=ffmpeg_params
            )
        except Exception as e:
            LOGGER.error(f"Error in seek_stream: {e}")
            raise CallError(f"Error seeking stream: {e}") from e

    async def speed_change(self, chat_id: int, speed: float = 1.0) -> None:
        """Change the playback speed (0.5x to 4.0x)."""
        if not 0.5 <= speed <= 4.0:
            raise ValueError("Speed must be between 0.5 and 4.0")

        curr_song = await chat_cache.get_current_song(chat_id)
        if not curr_song or not curr_song.file_path:
            raise ValueError("No song is currently playing in this chat!")

        try:
            await self.play_media(
                chat_id,
                curr_song.file_path,
                ffmpeg_parameters=f"-atend -filter:v setpts=0.5*PTS -filter:a atempo={speed}",
            )
        except Exception as e:
            LOGGER.error(f"Error changing speed for chat {chat_id}: {e}")
            raise CallError(f"Error changing speed: {e}") from e

    async def change_volume(self, chat_id: int, volume: int) -> None:
        """Change the volume of the current call."""
        try:
            client_name = await self._get_client_name(chat_id)
            await self.calls[client_name].change_volume_call(chat_id, volume)
        except Exception as e:
            LOGGER.error(f"Error changing volume for chat {chat_id}: {e}")
            raise CallError(f"Error changing volume: {e}") from e

    async def mute(self, chat_id: int) -> None:
        """Mute the current call."""
        try:
            client_name = await self._get_client_name(chat_id)
            await self.calls[client_name].mute(chat_id)
        except Exception as e:
            LOGGER.error(f"Error muting chat {chat_id}: {e}")
            raise CallError(f"Error muting call: {e}") from e

    async def unmute(self, chat_id: int) -> None:
        """Unmute the current call."""
        LOGGER.info(f"Unmuting stream for chat {chat_id}")
        try:
            client_name = await self._get_client_name(chat_id)
            await self.calls[client_name].unmute(chat_id)
        except Exception as e:
            LOGGER.error(f"Error unmuting chat {chat_id}: {e}")
            raise CallError(f"Error unmuting call: {e}") from e

    async def resume(self, chat_id: int) -> None:
        """Resume the current call."""
        LOGGER.info(f"Resuming stream for chat {chat_id}")
        try:
            client_name = await self._get_client_name(chat_id)
            await self.calls[client_name].resume(chat_id)
        except Exception as e:
            LOGGER.error(f"Error resuming chat {chat_id}: {e}")
            raise CallError(f"Error resuming call: {e}") from e

    async def pause(self, chat_id: int) -> None:
        """Pause the current call."""
        LOGGER.info(f"Pausing stream for chat {chat_id}")
        try:
            client_name = await self._get_client_name(chat_id)
            await self.calls[client_name].pause(chat_id)
        except Exception as e:
            LOGGER.error(f"Error pausing chat {chat_id}: {e}")
            raise CallError(f"Error pausing call: {e}") from e

    async def played_time(self, chat_id: int) -> int:
        """Get the played time of the current call."""
        LOGGER.info(f"Getting played time for chat {chat_id}")
        try:
            client_name = await self._get_client_name(chat_id)
            return await self.calls[client_name].time(chat_id)
        except exceptions.NotInCallError:
            await chat_cache.clear_chat(chat_id)
            return 0
        except Exception as e:
            LOGGER.error(f"Error getting played time for chat {chat_id}: {e}")
            raise CallError(f"Error getting played time: {e}") from e

    async def vc_users(self, chat_id: int) -> list:
        """Get the list of participants in the current call."""
        LOGGER.info(f"Getting VC users for chat {chat_id}")
        try:
            client_name = await self._get_client_name(chat_id)
            return await self.calls[client_name].get_participants(chat_id)
        except Exception as e:
            LOGGER.error(f"Error getting participants for chat {chat_id}: {e}")
            raise CallError(f"Error getting participants: {e}") from e

    async def stats_call(self, chat_id: int) -> tuple[float, float]:
        """Get call statistics (ping and CPU usage)."""
        try:
            client_name = await self._get_client_name(chat_id)
            return (
                self.calls[client_name].ping,
                await self.calls[client_name].cpu_usage,
            )
        except Exception as e:
            LOGGER.error(f"Error getting stats for chat {chat_id}: {e}")
            raise CallError(f"Error getting call stats: {e}") from e


async def start_clients() -> None:
    """Start PyTgCalls clients."""
    session_strings = [s for s in config.SESSION_STRINGS if s]
    if not session_strings:
        LOGGER.error("No STRING session provided. Exiting...")
        raise SystemExit(1)

    try:
        await asyncio.gather(
            *[
                call.start_client(config.API_ID, config.API_HASH, s)
                for s in session_strings
            ]
        )
        LOGGER.info("✅ Clients started successfully.")
    except Exception as exc:
        LOGGER.error(f"Error starting clients: {exc}", exc_info=True)
        raise SystemExit(1) from exc


call: MusicBot = MusicBot()
