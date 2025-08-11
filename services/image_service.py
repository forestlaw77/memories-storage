# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import base64
import hashlib
import json
import logging
import os
from http import HTTPStatus
from io import BytesIO
from typing import Any, Optional, Tuple, cast

from flask import Response, g, jsonify, request
from werkzeug.datastructures import FileStorage

from auth.verify_auth_token import get_user_id
from config.types import IMAGE_MIMETYPE_MAP, ImageFitMode
from manager.image_processor import image_processor
from models.types import ResourceMeta
from services.base_service import BaseService


class ImageService(BaseService):
    def __init__(self, storage_backend):
        super().__init__(storage_backend, "images")

    # Converts image content if resizing, format conversion, or other transformations are requested.
    def _optional_content_convert(
        self,
        resource_id: str,
        content_id: int,
        base_content: bytes,
        base_mimetype: Optional[str],
    ) -> dict:
        """
        Converts image content if additional processing is required.

        Args:
            resource_id (str): The ID of the resource being processed.
            content_id (str): The ID of the specific content item.
            base_content (bytes): The raw binary content of the image.
            base_mimetype (Optional[str]): The MIME type of the image content.

        Query Parameters:
            width (int, optional): Resize width.
            height (int, optional): Resize height.
            quality (int, optional): Compression quality (default: 85).
            format (str, optional): Output format (default: "webp").
            fit (str, optional): Image fitting mode ("cover" or "contain").
            keep_exif (bool, optional): Preserve EXIF data.

        Returns:
            dict: A structured response indicating whether the content was processed.

        Process:
            1. Parse request parameters for image transformations.
            2. Validate numerical input (`width`, `height`, `quality`).
            3. Check requested format conversion (`mimetype` based).
            4. Apply transformations if needed (resize, format change, compression).
            5. Return the processed image content or original content if no changes were made.

        Response Structure:
            {
                "status": "success",
                "message": "Resource content retrieved and processed successfully.",
                "resource_id": "<str>",
                "content_id": "<str>",
                "data": {
                    "content": <bytes>,
                    "mimetype": "<str>"
                }
            }
        """
        try:
            width = int(request.args.get("width", "0"))
            height = int(request.args.get("height", "0"))
            quality = int(request.args.get("quality", "0"))
        except ValueError:
            return self._generate_response_dict(
                status="error",
                message="Invalid numerical values for width, height, or quality.",
                resource_id=resource_id,
                content_id=content_id,
                error="Width, height, and quality must be valid integers.",
                status_code=HTTPStatus.BAD_REQUEST,
                data=None,
            )

        format = request.args.get("format", "").strip().lower()
        fit_mode = request.args.get("fit", "").strip().lower()
        keep_exif = request.args.get("keep_exif", "").strip().lower() in {
            "true",
            "yes",
            "1",
        }

        response = {}

        if not format and not width and not height and not quality and not fit_mode:
            # No conversion required, return original content
            return self._generate_response_dict(
                status="success",
                message="Resource content retrieved successfully.",
                resource_id=resource_id,
                content_id=content_id,
                data={"content": base_content, "mimetype": base_mimetype},
                status_code=HTTPStatus.OK,
            )

        converted_mimetype = IMAGE_MIMETYPE_MAP.get(format, "application/octet-stream")
        base_extension = base_mimetype.split("/")[1] if base_mimetype else None

        # Ensure HEIC conversion is not requested
        if converted_mimetype == "image/heic" and base_mimetype != "image/heic":
            return self._generate_response_dict(
                status="error",
                message="Conversion to HEIC is not supported.",
                resource_id=resource_id,
                content_id=content_id,
                error="It does not support conversion to HEIC.",
                status_code=HTTPStatus.BAD_REQUEST,
                data=None,
            )

        # Validate fitting mode
        if fit_mode not in ["", "cover", "contain"]:
            return self._generate_response_dict(
                status="error",
                message="Only 'cover' or 'contain' are allowed as fit modes.",
                resource_id=resource_id,
                content_id=content_id,
                error="An invalid fit_mode was specified.",
                status_code=HTTPStatus.BAD_REQUEST,
                data=None,
            )

        # Default values for missing parameters
        format = format if format else "webp"
        quality = quality if quality else 85
        fit_mode = fit_mode if fit_mode else "cover"

        # Temporary save path
        temp_file_path = f"/tmp/{resource_id}_{content_id}.{format.lower()}"
        content_buffer = BytesIO(base_content)

        # Apply image processing
        success = image_processor.convert_image(
            content_buffer,
            temp_file_path,
            None if format == base_extension else format,
            width,
            height,
            quality,
            ImageFitMode.COVER if fit_mode == "cover" else ImageFitMode.CONTAIN,
            keep_exif,
        )

        if not success:
            return self._generate_response_dict(
                status="error",
                message="Image processing failed.",
                resource_id=resource_id,
                content_id=content_id,
                error="An internal processing error occurred.",
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                data=None,
            )

        try:
            with open(temp_file_path, "rb") as f:
                content = f.read()
        except Exception as e:
            return self._generate_response_dict(
                status="error",
                message="Failed to load processed image file.",
                resource_id=resource_id,
                content_id=content_id,
                error=f"Failed to load processed image file: {e}",
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                data=None,
            )
        finally:
            # Remove temporary file
            try:
                os.remove(temp_file_path)
            except Exception as e:
                response = self._generate_response_dict(
                    response=response,
                    status="warning",
                    message="Failed to delete temporary file.",
                    resource_id=resource_id,
                    content_id=content_id,
                    error=f"Failed to delete temporary file {temp_file_path}: {e}",
                    status_code=HTTPStatus.OK,
                )

        return self._generate_response_dict(
            response=response,
            status="success",
            message="Resource content retrieved and processed successfully.",
            resource_id=resource_id,
            content_id=content_id,
            data={"content": content, "mimetype": converted_mimetype},
            status_code=HTTPStatus.OK,
        )

    def _optional_thumbnail_process(
        self,
        content_id: Optional[int] = None,
        resource_meta: Optional[ResourceMeta] = None,
        content_buffer: Optional[BytesIO] = None,
    ) -> Optional[BytesIO]:
        return content_buffer

    def get_image_address(self, resource_id: str) -> Response:
        from geopy.geocoders import Nominatim

        user_id: str = get_user_id(g.user_info, g.auth_provider)

        user_lock = self._get_user_lock(user_id)
        with user_lock:
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            resource_meta = self.storage_backend.load_resource_meta(
                user_id, self.resource_name, resource_id
            )

            if not resource_meta:
                return self._generate_response(
                    status="error",
                    message=f"Resource with ID '{resource_id}' not found.",
                    error=f"Resource {resource_id} not found in the storage backend",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            basic_meta = resource_meta.get("basic_meta")
            extra_info = basic_meta.get("extra_info") if basic_meta else None
            exif = extra_info.get("exif") if extra_info else None
            lat = exif.get("GPSLatitude") if exif else None
            lon = exif.get("GPSLongitude") if exif else None

            if not lat or not lon:
                return self._generate_response(
                    status="error",
                    message="No GPS data found.",
                    error="EXIF metadata does not contain GPSInfo.",
                    status_code=HTTPStatus.OK,
                )

            def get_address(lat, lon):
                geolocator = Nominatim(user_agent="Memories/1.0")
                location = geolocator.reverse((lat, lon))
                return location.address if location else "Unknown"  # type: ignore

            address = get_address(lat, lon)

            return self._generate_response(
                status="success",
                message="success",
                response_data={"address": address},
                status_code=HTTPStatus.OK,
            )

    def patch_content_exif(self, resource_id: str, content_id: int) -> Response:
        user_id: str = get_user_id(g.user_info, g.auth_provider)

        user_lock = self._get_user_lock(user_id)
        with user_lock:
            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Validate content ID
            response = self._validate_content_id(user_id, resource_id, content_id)
            if response.status_code != HTTPStatus.OK:
                return response
            content_id = int(content_id)

            update_items = request.json
            if not update_items:
                return self._generate_response(
                    status="error",
                    message="Missing update_items parameter",
                    error="Missing update_items parameter",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            content_bytes = self.storage_backend.load_resource_content(
                user_id, self.resource_name, resource_id, content_id
            )
            if not content_bytes:
                return self._generate_response(
                    status="error",
                    message="Failed to get content",
                    error="ailed to get content",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            content_file = image_processor.update_exif(
                BytesIO(content_bytes), "bin", update_items
            )

            if not isinstance(content_file, BytesIO):
                return self._generate_response(
                    status="error",
                    message="EXIF update failed",
                    error="update_exif returned False",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            else:
                self.storage_backend.save_resource(
                    user_id,
                    self.resource_name,
                    resource_id,
                    None,
                    content_file,
                    content_id,
                    content_file,  # re-make thumbnails
                )

            return self._generate_response(
                status="success",
                message="EXIF updated successfully",
                error=None,
                status_code=HTTPStatus.OK,
            )
