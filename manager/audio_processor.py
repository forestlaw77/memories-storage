# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed under the MIT License for non-commercial use.

import logging
import os
import subprocess
import tempfile
from io import BytesIO
from typing import Optional, Union
from urllib.parse import quote_plus

import requests
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis

from config.settings import MP3_TO_MIDI_ENABLE, SOUND_THUMBNAIL_ENABLE
from config.types import (
    AUDIO_CONVERTIBLE_FORMATS,
    AUDIO_FILETYPE_MAP,
    AUDIO_MIMETYPE_MAP,
)


class AudioProcessor:
    """Class for processing audio files, including format conversion and visualization."""

    def __init__(self):
        pass

    def extract_thumbnail_mp4(self, content_buffer: BytesIO) -> Optional[BytesIO]:
        """Extracts album art from an MP4/M4A file."""
        audio = MP4(fileobj=content_buffer)
        if audio.tags and "covr" in audio.tags:
            return BytesIO(audio.tags["covr"][0])
        return None

    def extract_thumbnail_mp3(self, audio_path: str) -> Optional[BytesIO]:
        """Extracts album art from an MP3 file."""
        audio = MP3(audio_path, ID3=ID3)
        if audio.tags and "APIC:" in audio.tags:
            return BytesIO(audio.tags["APIC:"].data)
        return None

    def extract_thumbnail_ogg(self, audio_path: str) -> Optional[BytesIO]:
        """Extracts album art from an OGG Vorbis file."""
        audio = OggVorbis(audio_path)
        if audio.tags and "METADATA_BLOCK_PICTURE" in audio.tags:
            return BytesIO(audio.tags["METADATA_BLOCK_PICTURE"][0])
        return None

    def extract_thumbnail_flac(self, audio_path: str) -> Optional[BytesIO]:
        """Extracts album art from a FLAC file."""
        audio = FLAC(audio_path)
        for picture in audio.pictures:
            if picture.type == 3:  # Type 3 = Cover (Front)
                return BytesIO(picture.data)
        return None

    def extract_audio_thumbnail(
        self, content_buffer: BytesIO, mimetype: str
    ) -> Optional[BytesIO]:
        """Extracts thumbnail from audio metadata."""
        logging.info("extract_audio_thumbnail")
        if mimetype in ["audio/x-m4a", "audio/mp4", "audio/aac"]:
            return self.extract_thumbnail_mp4(content_buffer)

        elif mimetype in ["audio/mpeg", "audio/flac", "audio/ogg", "audio/opus"]:
            suffix = AUDIO_FILETYPE_MAP.get(mimetype, "mp3")
            with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as tmp:
                tmp.write(content_buffer.getvalue())
                tmp_path = tmp.name
                try:
                    if mimetype == "audio/mpeg":
                        return self.extract_thumbnail_mp3(tmp_path)
                    elif mimetype == "audio/flac":
                        return self.extract_thumbnail_flac(tmp_path)
                    else:  # OGG / OPUS
                        return self.extract_thumbnail_ogg(tmp_path)
                finally:
                    os.remove(tmp_path)
        return None

    def convert_audio(
        self, format: str, content: bytes, mimetype: str
    ) -> Optional[bytes]:
        """Converts an audio file to the specified format.

        Args:
            format (str): The target audio format (e.g., 'mp3', 'wav').
            content (bytes): The binary content of the audio file.
            mimetype (str): The MIME type of the input file.

        Returns:
            Optional[bytes]: The binary content of the converted audio file,
            or None if the format is unsupported.

        Raises:
            ValueError: If the requested format conversion is not supported.
        """
        target_mimetype = AUDIO_MIMETYPE_MAP.get(format)
        base_format = AUDIO_FILETYPE_MAP.get(mimetype)

        # Skip conversion if the formats are the same
        if not format or format == base_format or target_mimetype == mimetype:
            return content

        # Check for unsupported conversions
        if format not in AUDIO_CONVERTIBLE_FORMATS or not base_format:
            logging.error(
                f"Unsupported conversion: Cannot convert '{mimetype}' to '{format}'."
            )
            raise ValueError(
                f"Unsupported conversion: Cannot convert '{mimetype}' to '{format}'."
            )

        # Create a temporary input/output file name
        input_path = tempfile.mktemp(suffix=f".{base_format}")
        output_path = tempfile.mktemp(suffix=f".{format}")
        logging.info(input_path)
        logging.info(output_path)
        try:
            # Save audio to a temporary file
            with open(input_path, "wb") as f:
                f.write(content)
            # Construct the `ffmpeg` command
            command = ["ffmpeg", "-i", input_path, output_path]

            subprocess.run(command, check=True, capture_output=True)
            # Read the converted audio data
            with open(output_path, "rb") as f:
                result_content = f.read()
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg conversion failed: {e.stderr.decode()}")
            raise RuntimeError(f"FFmpeg conversion failed: {e.stderr.decode()}") from e
        finally:
            # Clean up temporary files
            os.remove(input_path)
            os.remove(output_path)

        return result_content

    def _create_mp3_to_midi(self):
        def mp3_to_midi(self, content: bytes, base_format: str) -> Optional[bytes]:
            """
            Converts an MP3 (or other audio format) to MIDI using a transcription model.

            Args:
                content (bytes): Binary content of the audio file.
                base_format (str): Original format of the input file (e.g., 'mp3', 'wav').

            Returns:
                Optional[bytes]: MIDI file content if successful, otherwise None.

            Raises:
                ValueError: If transcription fails or an error occurs during processing.

            Process:
                1. Save the input audio file temporarily.
                2. Load the audio using `load_audio()` to ensure correct format.
                3. Use `PianoTranscription` to convert the audio into MIDI.
                4. Read and return the MIDI file content.
                5. Remove temporary files after processing.
            """
            if not MP3_TO_MIDI_ENABLE:
                logging.warning(
                    "MP3_TO_MIDI_ENABLE is set to False in config/settings.py"
                )
                return None

            try:
                import torch  # type: ignore
                from piano_transcription_inference import (  # type: ignore
                    PianoTranscription,
                    load_audio,
                    sample_rate,
                )

                device = (
                    torch.device("cuda")
                    if torch.cuda.is_available()
                    else torch.device("cpu")
                )
            except ModuleNotFoundError:
                logging.error(
                    "torch or piano_transcription_inference is not installed. MIDI transcription is disabled."
                )
                return None

            # Save the audio to a temporary file
            with tempfile.NamedTemporaryFile(
                suffix=f".{base_format}", delete=False
            ) as tmp:
                tmp.write(content)
                input_path = tmp.name

            # Create a temporary MIDI output file
            with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as output_tmp:
                output_path = output_tmp.name

            try:
                # Load the audio file for transcription
                audio, _ = load_audio(input_path, sr=sample_rate, mono=True)

                # Initialize transcription model
                transcriptor = PianoTranscription(device=device, checkpoint_path=None)

                # Perform transcription from audio to MIDI
                transcriptor.transcribe(audio, output_path)

                # Read the generated MIDI file
                with open(output_path, "rb") as f:
                    midi_data = f.read()

            except Exception as e:
                logging.error(f"Error during transcription: {e}")
                midi_data = None

            finally:
                # Clean up temporary files
                os.remove(input_path)
                os.remove(output_path)

            return midi_data

    def _load_audio_from_bytesio(self, content_buffer: BytesIO, filetype: str):
        """Loads an audio file from a BytesIO buffer."""
        import librosa  # type: ignore

        with tempfile.NamedTemporaryFile(suffix=f".{filetype}", delete=False) as tmp:
            tmp.write(content_buffer.getvalue())  # バイナリデータを書き込む
            tmp_path = tmp.name
            logging.info(tmp_path)

        try:
            y, sr = librosa.load(tmp_path, sr=None)
        except Exception as e:
            raise e  # 例外をそのまま伝える（元のエラー情報を保持）
        finally:
            try:
                os.remove(tmp_path)  # 確実に削除
            except OSError as err:
                logging.warning(f"Failed to remove temp file {tmp_path}: {err}")

        return y, sr

    def generate_waveform_thumbnail(
        self, audio_path: Union[str, BytesIO], filetype: str
    ) -> Optional[BytesIO]:
        """Generates a waveform thumbnail image from an audio file.

        Args:
            audio_path (Union[str, BytesIO]): Path to the audio file or BytesIO buffer.
            filetype (str): The format of the input audio file (e.g., 'mp3', 'wav').

        Returns:
            BytesIO: A buffer containing the generated waveform image in PNG format.
        """
        if not SOUND_THUMBNAIL_ENABLE:
            return None
        import librosa  # type: ignore
        import matplotlib.pyplot as plt  # type: ignore

        # Load the audio file with the original sample rate
        if isinstance(audio_path, BytesIO):
            y, sr = self._load_audio_from_bytesio(audio_path, filetype)
        else:
            y, sr = librosa.load(audio_path, sr=None)

        # Create a figure for visualization
        fig, ax = plt.subplots(figsize=(6, 2))

        # Display the waveform
        librosa.display.waveshow(y, sr=sr, ax=ax)

        # Hide axes for cleaner output
        ax.set_axis_off()

        # Save the figure to a binary buffer
        buffer = BytesIO()
        plt.savefig(buffer, format="png", bbox_inches="tight")
        plt.close(fig)
        buffer.seek(0)

        return buffer

    def generate_spectrogram_thumbnail(
        self, audio_path: Union[str, BytesIO], filetype: str
    ) -> Optional[BytesIO]:
        """
        Generates a spectrogram thumbnail image from an audio file.

        Args:
            audio_path (str): Path to the audio file.

        Returns:
            BytesIO: A buffer containing the generated spectrogram image in PNG format.
        """
        if not SOUND_THUMBNAIL_ENABLE:
            return None
        import librosa  # type: ignore
        import matplotlib.pyplot as plt  # type: ignore
        import numpy as np

        # Load the audio file
        if isinstance(audio_path, BytesIO):
            y, sr = self._load_audio_from_bytesio(audio_path, filetype)
        else:
            y, sr = librosa.load(audio_path, sr=None)

        # Compute the Short-Time Fourier Transform (STFT) and convert to decibel scale
        D = librosa.amplitude_to_db(np.abs(librosa.stft(y)), ref=np.max)

        # Create a spectrogram visualization
        fig, ax = plt.subplots(figsize=(6, 2))
        librosa.display.specshow(
            D, sr=sr, x_axis="time", y_axis="log", cmap="inferno", ax=ax
        )

        # Remove axes for cleaner output
        ax.set_axis_off()

        # Save spectrogram to a binary buffer
        buffer = BytesIO()
        plt.savefig(buffer, format="png", bbox_inches="tight")
        plt.close(fig)
        buffer.seek(0)

        return buffer

    def generate_piano_roll_thumbnail(
        self, midi_path: Union[str, BytesIO]
    ) -> Optional[BytesIO]:
        """
        Generates a piano roll image from a MIDI file.

        Args:
            midi_path (Union[str, BytesIO]): Path or binary content of the MIDI file.

        Returns:
            BytesIO: A buffer containing the piano roll image in PNG format.
        """
        if not SOUND_THUMBNAIL_ENABLE:
            return None
        import matplotlib.pyplot as plt  # type: ignore
        import mido  # type: ignore
        import numpy as np

        try:
            midi = mido.MidiFile(midi_path)
        except Exception as e:
            print(f"Error loading MIDI file: {e}")
            return BytesIO()

        max_ticks = midi.length * 480  # Estimated maximum length
        piano_roll = np.zeros((128, int(max_ticks)))  # 128 keys x time

        time_cursor = 0
        track_data = []

        for msg in midi.tracks[0]:  # Process first track
            if msg.type == "note_on" and msg.velocity > 0:
                track_data.append((msg.time, msg.note))

        # Convert MIDI data to matrix
        for time, note in track_data:
            time_cursor += time
            if time_cursor < piano_roll.shape[1]:  # Only within range
                piano_roll[note, time_cursor] = 1

        # Plot the piano roll
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.imshow(piano_roll, aspect="auto", cmap="inferno", origin="lower")
        ax.set_axis_off()

        # Save to buffer
        buffer = BytesIO()
        plt.savefig(buffer, format="png", bbox_inches="tight")
        plt.close(fig)
        buffer.seek(0)

        return buffer

    def fetch_artwork(self, album_name: str, artist_name: str) -> Optional[BytesIO]:
        """Fetches album artwork from iTunes or MusicBrainz and returns it as BytesIO."""

        # iTunes APIを試す
        artwork_url = self.fetch_itunes_artwork(album_name, artist_name)
        if not artwork_url:
            logging.warning(
                f"[fetch_artwork] No artwork found in iTunes, checking MusicBrainz..."
            )
            artwork_url = self.fetch_musicbrainz_artwork(album_name, artist_name)

        if not artwork_url:
            logging.error("[fetch_artwork] No artwork found from any source.")
            return None

        try:
            response = requests.get(artwork_url)
            if response.status_code == 200:
                return BytesIO(response.content)
            else:
                logging.error(
                    f"[fetch_artwork] Failed to fetch artwork: HTTP {response.status_code}"
                )
        except Exception as e:
            logging.error(f"[fetch_artwork] Error fetching artwork: {e}")

        return None

    def fetch_itunes_artwork(self, album_name: str, artist_name: str) -> Optional[str]:
        """Fetches album artwork URL from iTunes API with dynamic resizing."""
        query = quote_plus(f"{album_name} {artist_name}")
        url = f"https://itunes.apple.com/search?term={query}&media=music&entity=album&limit=1"

        try:
            response = requests.get(url)
            data = response.json()

            if data.get("resultCount", 0) > 0:
                original_url = data["results"][0].get("artworkUrl100", None)
                if original_url:
                    for size in ["600", "500", "400", "300", "200", "100"]:
                        modified_url = original_url.replace("100x100", f"{size}x{size}")
                        return modified_url

            logging.warning("[fetch_itunes_artwork] No valid artwork found.")

        except Exception as e:
            logging.error(f"[fetch_itunes_artwork] Error fetching iTunes artwork: {e}")

        return None

    def fetch_musicbrainz_artwork(
        self, album_name: str, artist_name: str
    ) -> Optional[str]:
        """Fetches album artwork URL from MusicBrainz API."""
        mbid = self.fetch_musicbrainz_release_id(album_name, artist_name)
        if mbid:
            return self.fetch_cover_art(mbid)
        return None

    def fetch_musicbrainz_release_id(
        self, album_name: str, artist_name: str
    ) -> Optional[str]:
        """Fetches MBID from MusicBrainz API for the given album and artist."""
        url = f"https://musicbrainz.org/ws/2/release/?query=release:{album_name} AND artist:{artist_name}&fmt=json"

        try:
            response = requests.get(url, headers={"User-Agent": "MyMusicApp/1.0"})
            data = response.json()

            if "releases" in data and len(data["releases"]) > 0:
                return data["releases"][0]["id"]  # 最初のリリースIDを取得

        except Exception as e:
            logging.error(
                f"[fetch_musicbrainz_release_id] Error fetching MusicBrainz ID: {e}"
            )

        return None

    def fetch_cover_art(self, mbid: str) -> Optional[str]:
        """Fetches album artwork URL from Cover Art Archive."""
        url = f"https://coverartarchive.org/release/{mbid}/front"

        try:
            response = requests.get(url)
            if response.status_code == 200:
                return url  # アートワークURLを返す
            elif response.status_code == 404:
                logging.warning(
                    f"[fetch_cover_art] No cover art found for MBID: {mbid}"
                )

        except Exception as e:
            logging.error(f"[fetch_cover_art] Error fetching cover art: {e}")

        return None


audio_processor = AudioProcessor()
