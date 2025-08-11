# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging
from http import HTTPStatus
from io import BytesIO
from typing import Optional

import requests
from flask import request
from pdf2image import convert_from_bytes
from PIL import Image

from config.types import DOCUMENT_MIMETYPE_MAP
from manager.document_processor import document_processor
from models.types import ResourceMeta
from services.base_service import BaseService


class DocumentService(BaseService):
    def __init__(self, storage_backend):
        super().__init__(storage_backend, "documents")

    # Processes an optional thumbnail from the provided metadata.
    def _optional_thumbnail_process(
        self,
        content_id: Optional[int] = None,
        resource_meta: Optional[ResourceMeta] = None,
        content_buffer: Optional[BytesIO] = None,
    ) -> Optional[BytesIO]:
        """
        Retrieves and processes a thumbnail from the provided metadata.

        Args:
            detail_meta (Optional[Dict[str, any]]): Metadata containing 'cover_image_url'.
            content_buffer (Optional[BytesIO]): Unused but reserved for potential future use.

        Returns:
            Optional[BytesIO]: Processed thumbnail as a BytesIO object, or None if retrieval fails.

        Process:
            1. Validate metadata and retrieve `cover_image_url`.
            2. Download the image with a timeout for reliability.
            3. Apply Pillow transformations (resize, format conversion).
            4. Return processed thumbnail in `WEBP` format.
        """

        if not resource_meta:
            # If no metadata is provided, return None
            return None
        basic_meta = resource_meta.get("basic_meta")
        detail_meta = resource_meta.get("detail_meta")

        if detail_meta:
            thumbnail_url = detail_meta.get("cover_image_url")
            if thumbnail_url:
                try:
                    # Download image from the provided URL
                    response = requests.get(
                        thumbnail_url,
                        headers={"User-Agent": "Mozilla/5.0"},
                        timeout=10,
                    )

                    if response.status_code == 200:
                        # Open image and process it
                        image = Image.open(BytesIO(response.content))
                        image.thumbnail((640, 400))  # Resize to fit within 640x400
                        output = BytesIO()
                        image.save(output, format="WEBP")  # Convert to WEBP format
                        output.seek(0)  # Reset buffer position for further usage
                        return output
                    logging.error(
                        f"[_optional_thumbnail_process] Failed to download image, status code: {response.status_code}"
                    )

                except Exception as e:
                    logging.error(
                        f"[_optional_thumbnail_process] Error downloading or processing thumbnail: {e}"
                    )

        if content_id is None or not basic_meta or not content_buffer:
            return None

        contents = basic_meta.get("contents")
        if not contents:
            # If no contents, return None
            return None
        target_content = next(
            (content for content in contents if content.get("id") == content_id), None
        )
        if not target_content:
            # If no target content found, return None
            return None
        mimetype = target_content.get("mimetype")
        if mimetype == "application/pdf":
            try:
                # If the content is a PDF, convert the first page to an image
                images = convert_from_bytes(
                    content_buffer.getvalue(),
                    size=(300, 300),
                    first_page=1,
                    last_page=1,
                )
                thumbnail_buffer = BytesIO()
                images[0].save(
                    thumbnail_buffer, format="JPEG"
                )  # 1ページ目をサムネイルに
                thumbnail_buffer.seek(0)  # Reset buffer position for further usage
                return thumbnail_buffer
            except Exception as e:
                logging.error(
                    f"[_optional_thumbnail_process] Error convert the PDF first page to an image.{{e}}"
                )

        return None

    def _optional_content_convert(
        self,
        resource_id: str,
        content_id: int,
        base_content: bytes,
        base_mimetype: str,
    ) -> dict:
        """
        Converts book content if additional processing is required.

        Args:
            resource_id (str): The ID of the resource being processed.
            content_id (int): The ID of the specific content item.
            base_content (bytes): The raw binary content of the book.
            base_mimetype (Optional[str]): The MIME type of the book content.

        Returns:
            dict: A structured response indicating whether the content was processed.
        """
        format = request.args.get("format", None)
        if not format:
            return self._generate_response_dict(
                status="success",
                message="Book content processed successfully.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.OK,
                data={"content": base_content, "mimetype": base_mimetype},
            )

        try:
            result_content = document_processor.convert_document(
                format, base_content, base_mimetype
            )
            result_mimetype = DOCUMENT_MIMETYPE_MAP.get(format)
        except ValueError:
            return self._generate_response_dict(
                status="error",
                message=f"Conversion to {format} is not supported.",
                resource_id=resource_id,
                content_id=content_id,
                error=f"It does not support conversion to {format}.",
                status_code=HTTPStatus.BAD_REQUEST,
                data=None,
            )
        except Exception as e:
            return self._generate_response_dict(
                status="error",
                message="Book format conversion failed.",
                error=f"Book format conversion failed. ({e})",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                data=None,
            )

        return self._generate_response_dict(
            status="success",
            message="Book content processed successfully.",
            resource_id=resource_id,
            content_id=content_id,
            status_code=HTTPStatus.OK,
            data={"content": result_content, "mimetype": result_mimetype},
        )
