# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed under the MIT License for non-commercial use.tt

import logging
import re
import subprocess
import tempfile
from typing import Optional

from config.types import VIDEO_CONVERTIBLE_FORMATS, VIDEO_FILETYPE_MAP


class VideoProcessor:
    """Class for processing video files, including format conversion."""

    VIDEO_CODEC_MAP = {
        "mp4": "libx264",
        "avi": "mpeg4",
        "webm": "libvpx",
        "mov": "prores",
        "mkv": "libx264",
    }

    def convert_video(
        self, format: str, content: bytes, mimetype: str, output_resolution: str
    ) -> Optional[bytes]:
        """Converts a video file to the specified format and resolution.

        Args:
            format (str): The target video format (e.g., 'mp4', 'avi').
            content (bytes): The binary content of the video file.
            mimetype (str): The MIME type of the input file.
            output_resolution (str): The desired resolution for the output video.

        Returns:
            Optional[bytes]: The binary content of the converted video file,
            or None if the format is unsupported.

        Raises:
            ValueError: If the specified format is not supported for conversion.
            RuntimeError: If the video conversion fails.
        """
        base_format = VIDEO_FILETYPE_MAP.get(mimetype)
        if base_format is None:
            raise ValueError(f"Unsupported MIME type: {mimetype}")

        if not format or format.lower() == base_format.lower():
            return content
        if format not in VIDEO_CONVERTIBLE_FORMATS:
            supported_formats = ", ".join(VIDEO_CONVERTIBLE_FORMATS)
            raise ValueError(
                f"Unsupported conversion: '{mimetype}' to '{format}'. Supported formats: {supported_formats}"
            )
        if format not in self.VIDEO_CODEC_MAP:
            logging.warning(
                f"[convert_video] No codec mapping for format: {format}. Defaulting to 'libx264'."
            )

        codec = self.VIDEO_CODEC_MAP.get(format, "libx264")
        if not codec:
            raise ValueError(f"Unsupported video format: {format}")

        result_content = None

        # Create a temporary file for the output video
        with tempfile.NamedTemporaryFile(
            suffix=f".{format}", delete=True
        ) as output_tmp:
            output_path = output_tmp.name

            # Create a temporary file for the input video
            with tempfile.NamedTemporaryFile(
                suffix=f".{base_format}", delete=True
            ) as input_tmp:
                input_tmp.write(content)
                input_path = input_tmp.name

                # Construct the `ffmpeg` command
                command = [
                    "ffmpeg",
                    "-i",
                    input_path,
                    "-c:v",
                    codec,  # Video codec
                    "-preset",
                    "fast",
                    "-y",  # Overwrite output file if it exists
                    "-loglevel",
                    "error",  # Suppress ffmpeg's verbose output
                    "-hide_banner",  # Hide the startup banner
                    output_path,
                ]

                # If resolution is provided, ensure safe handling and apply scaling
                if output_resolution:
                    if not re.match(r"^\d+x\d+$", output_resolution):
                        raise ValueError(
                            f"Invalid resolution format: {output_resolution}"
                        )
                    command.insert(3, "-vf")
                    command.insert(4, f"scale={output_resolution}")

                try:
                    subprocess.run(command, check=True, capture_output=True)
                except subprocess.CalledProcessError as e:
                    error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
                    raise RuntimeError(f"Video conversion failed: {error_msg}")

            # Read the converted video data
            with open(output_path, "rb") as f:
                result_content = f.read()

        # Check if the result content is empty
        if not result_content:
            raise RuntimeError("Conversion succeeded, but output file is empty.")

        return result_content


video_processor = VideoProcessor()
