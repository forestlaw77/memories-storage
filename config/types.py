# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

from enum import Enum

DOCUMENT_MIMETYPE_MAP = {
    "txt": "text/plain",
    "pdf": "application/pdf",
    "epub": "application/epub+zip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xps": "application/vnd.ms-xpsdocument",
    "cbz": "application/x-cbz",
    "fb2": "application/x-fictionbook+xml",
    "mobi": "application/x-mobipocket-ebook",
}
"""dict: Mapping of document file extensions to MIME types."""

DOCUMENT_FILETYPE_MAP = {v: k for k, v in DOCUMENT_MIMETYPE_MAP.items()}
"""dict: Reverse mapping of document MIME types to file extensions."""

DOCUMENT_CONVERTIBLE_FORMATS = ["docx", "epub", "pdf", "txt"]
"""list: List of document formats that support conversion."""

IMAGE_MIMETYPE_MAP = {
    "heic": "image/heic",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
"""dict: Mapping of image file extensions to MIME types."""

IMAGE_FILETYPE_MAP = {v: k for k, v in IMAGE_MIMETYPE_MAP.items()}
"""dict: Reverse mapping of image MIME types to file extensions."""
IMAGE_FILETYPE_MAP["image/jpeg"] = "jpg"

AUDIO_MIMETYPE_LIST = {
    "audio/mpeg",
    "audio/wav",
    "audio/flac",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "audio/mp4",
    "audio/aac",
    "audio/ogg",
    "audio/opus",
    "audio/midi",
    "audio/midi",
    "audio/x-aiff",
    "audio/ape",
    "audio/x-wavpack",
    "audio/x-musepack",
}

AUDIO_MIMETYPE_MAP = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "m4a": "audio/x-m4a",
    "m4p": "audio/mp4",
    "aac": "audio/aac",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "mid": "audio/midi",
    "midi": "audio/midi",
    "aiff": "audio/x-aiff",
    "ape": "audio/ape",
    "wv": "audio/x-wavpack",
    "mpc": "audio/x-musepack",
}
"""dict: Mapping of audio file extensions to MIME types."""

AUDIO_FILETYPE_MAP = {v: k for k, v in AUDIO_MIMETYPE_MAP.items()}
AUDIO_FILETYPE_MAP["audio/midi"] = "mid"
AUDIO_FILETYPE_MAP["audio/mp4"] = "m4a"
"""dict: Reverse mapping of audio MIME types to file extensions."""

AUDIO_CONVERTIBLE_FORMATS = list(AUDIO_MIMETYPE_MAP.keys())


VIDEO_MIMETYPE_MAP = {
    "mov": "video/quicktime",
    "mp4": "video/mp4",
    "avi": "video/x-msvideo",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
}
"""dict: Mapping of video file extensions to MIME types."""

VIDEO_FILETYPE_MAP = {v: k for k, v in VIDEO_MIMETYPE_MAP.items()}
"""dict: Reverse mapping of video MIME types to file extensions."""

VIDEO_CONVERTIBLE_FORMATS = list(VIDEO_MIMETYPE_MAP.keys())

FULL_MIMETYPE_MAP = {
    **DOCUMENT_MIMETYPE_MAP,
    **IMAGE_MIMETYPE_MAP,
    **AUDIO_MIMETYPE_MAP,
    **VIDEO_MIMETYPE_MAP,
}
"""dict: Comprehensive mapping of file extensions to MIME types."""

FULL_FILETYPE_MAP = {v: k for k, v in FULL_MIMETYPE_MAP.items()}
FULL_FILETYPE_MAP["image/jpeg"] = "jpg"
"""dict: Reverse mapping of all MIME types to file extensions."""


ALLOWED_FILE_MIME_TYPES = {
    "images": IMAGE_FILETYPE_MAP,
    "books": DOCUMENT_FILETYPE_MAP,
    "documents": DOCUMENT_FILETYPE_MAP,
    "music": AUDIO_FILETYPE_MAP,
    "videos": VIDEO_FILETYPE_MAP,
}
"""dict: Allowed MIME types categorized by resource type."""


class ImageFitMode(Enum):
    """Enum representing image fit modes."""

    CONTAIN = "contain"
    COVER = "cover"


THUMBNAIL_SIZES = {
    "small": (100, 100),
    "medium": (150, 150),
    "large": (300, 300),
}
"""dict: Standard thumbnail sizes with corresponding width and height values."""
