# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

from typing import Any, Optional, TypedDict


class ExtraInfo(
    TypedDict, total=False
):  # Using total=False makes properties optional, providing flexibility.
    exif: dict[str, Any]  # File information obtainable with exiftools
    location: dict[str, Any]  # Geolocation information


class ContentMeta(TypedDict):
    """Defines metadata related to a content resource."""

    id: int  # Unique identifier of the content
    filename: str  # Name of the file
    mimetype: str  # MIME type of the content
    hash: str  # Hash of the content for integrity validation
    size: Optional[int]  # Size of the content in bytes
    created_at: str  # Timestamp when the content was created (ISO 8601 format)
    updated_at: str  # Timestamp when the content was last updated (ISO 8601 format)
    extra_info: Optional[ExtraInfo]  # Additional metadata specific to the content
    file_path: Optional[str]
    stored: bool


class BasicMeta(TypedDict):
    """Represents the fundamental metadata common to all resource types."""

    created_at: str  # Timestamp when the resource was created (ISO 8601 format)
    updated_at: str  # Timestamp when the resource was last updated (ISO 8601 format)
    content_ids: list[int]  # List of associated content IDs
    contents: list[ContentMeta]  # List of content metadata associated with the resource
    extra_info: Optional[ExtraInfo]  # Resource-specific additional metadata
    child_resource_ids: Optional[list[str]]  # Nested resources within a resource
    parent_resource_ids: Optional[list[str]]  # Parent resources


class DetailMeta(TypedDict):
    """User-defined metadata that allows flexible extensions for different use cases."""

    metadata: dict[str, Any]  # Arbitrary user-defined metadata


class ResourceMeta(TypedDict):
    """Aggregates metadata related to a resource, including basic and detailed metadata."""

    basic_meta: Optional[BasicMeta]  # Fundamental metadata shared across resource types
    detail_meta: Optional[DetailMeta]  # Resource-specific detailed metadata
