# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging
import subprocess
from http import HTTPStatus
from io import BytesIO
from typing import Optional, cast

from flask import request
from werkzeug.datastructures import FileStorage

from config.types import AUDIO_FILETYPE_MAP, AUDIO_MIMETYPE_MAP
from manager.audio_processor import audio_processor
from models.types import BasicMeta, ResourceMeta
from services.base_service import BaseService


class MusicService(BaseService):
    def __init__(self, storage_backend):
        super().__init__(storage_backend, "music")

    def _optional_thumbnail_process(
        self,
        content_id: Optional[int] = None,
        resource_meta: Optional[ResourceMeta] = None,
        content_buffer: Optional[BytesIO] = None,
    ) -> Optional[BytesIO]:
        """Generates a resource-specific thumbnail for audio content.

        If an album artwork exists within the audio file, it is extracted.
        Otherwise, an external lookup (iTunes or MusicBrainz) is performed.
        """

        if content_id is None or resource_meta is None or content_buffer is None:
            return None

        try:
            basic_meta = resource_meta.get("basic_meta", {}) or {}
            contents = basic_meta.get("contents", []) or []

            # Content ID に一致するデータを取得
            existing_content = next(
                (
                    content
                    for content in contents
                    if int(content.get("id", -1)) == content_id
                ),
                None,
            )
            if not existing_content:
                logging.error("[_optional_thumbnail_process] Content not found")
                return None

            mimetype = existing_content.get("mimetype", "application/octet-stream")

            # アルバム情報の取得
            extra_info = basic_meta.get("extra_info", {}) or {}
            exif = extra_info.get("exif", {}) or {}
            album_name = exif.get("Album", "").strip()
            artist_name = exif.get("Artist", "").strip()

        except Exception as e:
            logging.error(
                f"[_optional_thumbnail_process] Metadata extraction error: {e}"
            )
            return None

        try:
            # まずオーディオファイルからサムネイルを取得
            thumbnail = audio_processor.extract_audio_thumbnail(
                content_buffer, mimetype
            )

            if thumbnail:
                return thumbnail

            # もしオーディオファイル内にサムネイルがない場合は、アルバムアートワークを取得
            if album_name and artist_name:
                logging.info(
                    f"[_optional_thumbnail_process] Fetching artwork for {album_name} by {artist_name}"
                )
                return audio_processor.fetch_artwork(album_name, artist_name)

            return None

        except Exception as e:
            logging.error(
                f"[_optional_thumbnail_process] Thumbnail or artwork processing error: {e}"
            )
            return None

        # generators = {
        #     "audio/mp3": audio_processor.generate_spectrogram_thumbnail,
        #     "audio/wav": audio_processor.generate_waveform_thumbnail,
        #     "audio/flac": audio_processor.generate_spectrogram_thumbnail,
        #     "audio/aac": audio_processor.generate_spectrogram_thumbnail,
        #     "audio/x-m4a": audio_processor.generate_spectrogram_thumbnail,
        #     "audio/ogg": audio_processor.generate_spectrogram_thumbnail,
        #     "audio/midi": audio_processor.generate_piano_roll_thumbnail,
        # }

        # if mimetype in generators:
        #     try:
        #         thumbnail_func = generators.get(mimetype)
        #         return (
        #             thumbnail_func(content_buffer, AUDIO_FILETYPE_MAP.get(mimetype))
        #             if thumbnail_func
        #             else None
        #         )
        #     except Exception as e:
        #         logging.error(f"Error: Music _optional_thumbnail_process ({e})")
        #         return None
        # else:
        #     logging.error(
        #         "Error: Music _optional_thumbnail_process. Unsupported mimetype"
        #     )

        # return None

    def _optional_content_convert(
        self,
        resource_id: str,
        content_id: int,
        base_content: bytes,
        base_mimetype: str,
    ) -> dict:
        """
        Converts resource content if required by the resource type.

        Args:
            resource_id (str): The ID of the resource being processed.
            content_id (str): The ID of the specific content item.
            base_content (bytes): The raw binary content of the resource.
            base_mimetype (str): The MIME type of the content.

        Returns:
            dict: A structured response indicating successful content retrieval and processing.

        Process:
            1. Accepts raw binary content and MIME type.
            2. Applies resource-specific processing logic if needed.
            3. Returns processed content while preserving the MIME type.

        Response Structure:
            {
                "status": "success",
                "message": "Resource content retrieved and processed successfully.",
                "resource_id": "<str>",
                "content_id": "<str>",
                "error": None,
                "status_code": HTTPStatus.OK,
                "data": {
                    "content": <bytes>,
                    "mimetype": "<str>"
                }
            }
        """
        format = request.args.get("format", "").strip().lower()
        base_format = AUDIO_FILETYPE_MAP.get(base_mimetype, None)

        if not format or format == base_format:
            return self._generate_response_dict(
                status="success",
                message="Music content processed successfully.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.OK,
                data={"content": base_content, "mimetype": base_mimetype},
            )
        try:
            target_mimetype = AUDIO_MIMETYPE_MAP.get(format, None)
            if not target_mimetype or not base_format:
                logging.error(
                    f"[_optional_content_convert] error: Unsupported conversion '{base_format}' to '{format}'."
                )
                raise ValueError(
                    f"Unsupported conversion: '{base_format}' to '{format}'."
                )
            result_content = audio_processor.convert_audio(
                format, base_content, base_mimetype
            )
        except ValueError as e:
            return self._generate_response_dict(
                status="error",
                message=f"Conversion to {format} is not supported.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.BAD_REQUEST,
                data=None,
            )
        except subprocess.CalledProcessError as e:
            return self._generate_response_dict(
                status="error",
                message="Music conversion failed.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                data=None,
            )
        except Exception as e:
            return self._generate_response_dict(
                status="error",
                message="Music processing failed.",
                error=str(e),
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                data=None,
            )
        return self._generate_response_dict(
            status="success",
            message="Music content processed successfully.",
            resource_id=resource_id,
            content_id=content_id,
            status_code=HTTPStatus.OK,
            data={"content": result_content, "mimetype": target_mimetype},
        )

        # format = request.args.get("format", "").strip().lower()
        # base_format = FULL_FILETYPE_MAP.get(base_mimetype, None)
        # result_mimetype = FULL_MIMETYPE_MAP.get(format, None)
        # if (
        #     not format
        #     or not base_format
        #     or not result_mimetype
        #     or format == base_format
        # ):
        #     return self._generate_response_dict(
        #         status="success",
        #         message="Music content processed successfully.",
        #         resource_id=resource_id,
        #         content_id=content_id,
        #         status_code=HTTPStatus.OK,
        #         data={"content": base_content, "mimetype": base_mimetype},
        #     )

        # try:
        #     # 一時ファイルに音楽を保存
        #     with tempfile.NamedTemporaryFile(
        #         suffix=f".{base_format}", delete=False
        #     ) as tmp:
        #         tmp.write(base_content)
        #         input_path = tmp.name

        #     # 出力用の一時ファイル
        #     output_suffix = f".{format}"
        #     # output_resolution = "640x480" if format == "vga" else "1920x1080"

        #     with tempfile.NamedTemporaryFile(
        #         suffix=output_suffix, delete=False
        #     ) as output_tmp:
        #         output_path = output_tmp.name

        #     # `ffmpeg` コマンドを構成
        #     command = ["ffmpeg", "-i", input_path, output_path]

        #     subprocess.run(command, check=True)

        #     # 変換後の音楽データを取得
        #     with open(output_path, "rb") as f:
        #         result_content = f.read()

        #     # クリーンアップ
        #     os.remove(input_path)
        #     os.remove(output_path)

        # except subprocess.CalledProcessError as e:
        #     logging.error(f"FFmpeg conversion error: {e}")
        #     return self._generate_response_dict(
        #         status="error",
        #         message=f"Music conversion to {format} failed.",
        #         resource_id=resource_id,
        #         content_id=content_id,
        #         status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        #         data=None,
        #     )
        # except Exception as e:
        #     logging.error(f"Unexpected error in music processing: {e}")
        #     return self._generate_response_dict(
        #         status="error",
        #         message="Music processing failed.",
        #         error=str(e),
        #         resource_id=resource_id,
        #         content_id=content_id,
        #         status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        #         data=None,
        #     )

        # return self._generate_response_dict(
        #     status="success",
        #     message="Music content processed successfully.",
        #     resource_id=resource_id,
        #     content_id=content_id,
        #     status_code=HTTPStatus.OK,
        #     data={"content": result_content, "mimetype": result_mimetype},
        # )


# import subprocess


# def convert_audio_ffmpeg(input_path: str, output_path: str, output_format: str) -> None:
#     command = ["ffmpeg", "-i", input_path, output_path]
#     subprocess.run(command, check=True)


# convert_audio_ffmpeg("input.mp3", "output.wav", "wav")  # MP3 → WAV
# convert_audio_ffmpeg("input.wav", "output.flac", "flac")  # WAV → FLAC


# from pydub import AudioSegment


# def convert_audio(input_path: str, output_path: str, output_format: str) -> None:
#     audio = AudioSegment.from_file(input_path)
#     audio.export(output_path, format=output_format)


# convert_audio("input.mp3", "output.wav", "wav")  # 🎵 MP3 → WAV
# convert_audio("input.wav", "output.flac", "flac")  # 🎵 WAV → FLAC

# import numpy as np
# import librosa
# import librosa.display
# import matplotlib.pyplot as plt
# from io import BytesIO


# def generate_waveform_thumbnail(audio_path: str) -> BytesIO:
#     y, sr = librosa.load(audio_path, sr=None)  # 音声データを読み込む

#     fig, ax = plt.subplots(figsize=(6, 2))
#     librosa.display.waveshow(y, sr=sr, ax=ax)
#     ax.set_axis_off()

#     buffer = BytesIO()
#     plt.savefig(buffer, format="png", bbox_inches="tight")
#     plt.close(fig)

#     buffer.seek(0)
#     return buffer


# def generate_spectrogram_thumbnail(audio_path: str) -> BytesIO:
#     y, sr = librosa.load(audio_path, sr=None)
#     D = librosa.amplitude_to_db(np.abs(librosa.stft(y)), ref=np.max)

#     fig, ax = plt.subplots(figsize=(6, 2))
#     librosa.display.specshow(
#         D, sr=sr, x_axis="time", y_axis="log", cmap="inferno", ax=ax
#     )
#     ax.set_axis_off()

#     buffer = BytesIO()
#     plt.savefig(buffer, format="png", bbox_inches="tight")
#     plt.close(fig)

#     buffer.seek(0)
#     return buffer

# import mido
# import numpy as np
# import matplotlib.pyplot as plt
# from io import BytesIO


# def generate_piano_roll_thumbnail(midi_path: str) -> BytesIO:
#     """
#     Generates a piano roll image from a MIDI file.

#     Args:
#         midi_path (str): Path to the MIDI file.

#     Returns:
#         BytesIO: Piano roll image as a binary stream.
#     """
#     midi = mido.MidiFile(midi_path)
#     max_ticks = midi.length * 480  # 推定最大長 (480 ticks per quarter note)
#     track_data = []

#     for msg in midi.tracks[0]:  # 最初のトラックを処理
#         if msg.type == "note_on" and msg.velocity > 0:
#             track_data.append((msg.time, msg.note))

#     # 時間とノート番号を行列に変換
#     piano_roll = np.zeros((128, int(max_ticks)))  # 128鍵盤 × MIDI 長さ
#     time_cursor = 0

#     for time, note in track_data:
#         time_cursor += time
#         if time_cursor < piano_roll.shape[1]:  # 範囲内なら描画
#             piano_roll[note, time_cursor] = 1

#     # 可視化
#     fig, ax = plt.subplots(figsize=(6, 2))
#     ax.imshow(piano_roll, aspect="auto", cmap="inferno", origin="lower")
#     ax.set_xlabel("Time")
#     ax.set_ylabel("MIDI Note")
#     ax.set_title("MIDI Piano Roll")
#     ax.set_axis_off()

#     buffer = BytesIO()
#     plt.savefig(buffer, format="png", bbox_inches="tight")
#     plt.close(fig)

#     buffer.seek(0)
#     return buffer
