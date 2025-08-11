# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import base64
import datetime
import hashlib
import inspect
import logging
import os
import tempfile
import threading
from http import HTTPStatus
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from flask import Response, g, json, jsonify, make_response, request, send_file
from geopy.geocoders import Nominatim
from geopy.location import Location
from werkzeug.datastructures import FileStorage

from auth.verify_auth_token import get_user_id
from config.types import (
    ALLOWED_FILE_MIME_TYPES,
    FULL_FILETYPE_MAP,
    THUMBNAIL_SIZES,
    ImageFitMode,
)
from manager.content_id_manager import ContentIdManager
from manager.image_processor import image_processor
from manager.resource_id_manager import ResourceIdManager
from models.types import BasicMeta, ContentMeta, DetailMeta, ExtraInfo, ResourceMeta
from storage.abstract_backend import AbstractStorageBackend
from utils.file_utils import get_mimetype, sanitize_filename


class BaseService:
    """
    BaseService class for managing resources and their metadata.
    This class provides methods for creating, updating, and retrieving resources,
    as well as handling content and thumbnail generation.
    """

    def __init__(self, storage_backend: AbstractStorageBackend, resource_name: str):
        """
        Initializes the BaseService with a storage backend and resource name.
        Args:
            storage_backend (AbstractStorageBackend): The storage backend for resource management.
            resource_name (str): The name of the resource type.
        """
        self.storage_backend: AbstractStorageBackend = storage_backend
        self.resource_name: str = resource_name
        self.resource_id_manager: ResourceIdManager = ResourceIdManager(
            resource_name, storage_backend
        )
        self.user_locks: dict[str, threading.RLock] = {}
        self.content_id_manager = ContentIdManager(resource_name, storage_backend)

    # Returns a lock specific to the given user.
    def _get_user_lock(self, user_id: str) -> threading.RLock:
        """
        Returns a lock specific to the given user.

        This method retrieves an existing reentrant lock for the given user ID.
        If a lock does not exist for the user, it creates a new one and stores it.

        Args:
            user_id (str): The ID of the user.

        Returns:
            threading.RLock: The reentrant lock associated with the user.
        """
        if user_id not in self.user_locks:
            self.user_locks[user_id] = (
                threading.RLock()
            )  # Create only if it doesn't exist
        return self.user_locks[user_id]

    # Validates the content file format.
    def _validate_content_format(
        self, resource_type, content_file
    ) -> Optional[tuple[str, str, str, BytesIO]]:
        """
        Validates the content file format.
        Returns the mimetype, filename, extension, and buffer if valid, otherwise None.

        Args:
            resource_type: The type of the resource being processed.
            content_file: The file-like object containing the content.

        Returns:
            tuple[str, str, str, BytesIO] | None: A tuple containing the mimetype (str),
                filename (str), extension (str), and a BytesIO buffer of the content
                if the format is valid. Returns None otherwise.
        """
        if not content_file:
            logging.info(f"[_validate_content_formart] missing content_file")
            return None

        content_file.seek(0)
        buffer = BytesIO(content_file.read())
        allowed_types = ALLOWED_FILE_MIME_TYPES.get(resource_type, {})
        logging.info("allowed types:", allowed_types)
        mimetype = get_mimetype(content_file)

        if mimetype not in allowed_types:
            logging.info(
                f"[_validate_content_formart] {mimetype} is not allowed {resource_type}"
            )
            return None

        raw_filename = getattr(content_file, "filename", None)
        filename = sanitize_filename(raw_filename) if raw_filename else None
        if filename is None:
            logging.info(f"[_validate_content_formart] invalid filename {raw_filename}")
            return None

        extension = os.path.splitext(filename)[1][1:] if filename else None
        if extension is None:
            logging.info(f"[_validate_content_formart] missing extension")
            return None

        return (mimetype, filename, extension, buffer)

    # Creates the metadata for a new resource.
    def _make_resource_meta(
        self,
        detail_meta: Optional[DetailMeta] = None,
        content_id: Optional[int] = None,
        content_meta: Optional[ContentMeta] = None,
    ) -> ResourceMeta:
        """
        Creates a structured metadata object for a new resource.

        Args:
            detail_meta (Optional[Dict[str, Any]]): Detailed metadata containing
                user-editable information (e.g., title, author, publisher). Defaults to None.
            content_id (Optional[int]): Unique identifier for a content item, if applicable. Defaults to None.
            content_meta (Optional[Dict[str, Any]]): Metadata related to a specific content,
                such as available formats or content URL. Defaults to None.

        Returns:
            Dict[str, Any]: A structured resource metadata dictionary.

        Structure:
            {
                "basic_meta": {  # System-managed metadata (non-editable by users)
                    "created_at": <ISO timestamp>,
                    "updated_at": <ISO timestamp>,
                    "content_ids": [<int>, ...],  # List of associated content IDs
                    "contents": [<content_meta>, ...],  # List of content metadata
                },
                "detail_meta": {  # User-editable metadata
                    "title": <str>,
                    "description": <str>,
                    "author": <str>,
                    "publishedDate": <str>,
                    "publisher": <str>,
                    "isbn": <str>,
                    "cover_image_url": <str>,
                }
            }
        """
        now_datetime = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # System-managed metadata
        basic_meta: BasicMeta = {
            "created_at": now_datetime,
            "updated_at": now_datetime,  # New resource, so timestamps are identical
            "content_ids": [],  # Maintain a unique list of associated content IDs
            "contents": [],  # Store metadata related to contents
            "extra_info": {},  # Placeholder for resource-specific metadata
            "child_resource_ids": [],
            "parent_resource_ids": [],
        }

        if content_id and content_meta:
            basic_meta["content_ids"] = list(
                set(basic_meta["content_ids"]) | {content_id}
            )
            basic_meta["contents"].append(content_meta)

        # Structured resource metadata
        resource_meta: ResourceMeta = {
            "basic_meta": basic_meta,
            "detail_meta": detail_meta,
        }

        return resource_meta

    # Updates the metadata of an existing resource.
    def _update_resource_meta(
        self,
        user_id: str,
        resource_id: str,
        detail_meta: Optional[DetailMeta] = None,
        content_id: Optional[int] = None,
        content_meta: Optional[ContentMeta] = None,
    ) -> Optional[ResourceMeta]:
        """
        Updates the metadata of an existing resource.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The ID of the resource to update.
            detail_meta (Optional[Dict[str, Any]]): User-editable detailed metadata, such as
                title, description, author, and publisher. Defaults to None.
            content_id (Optional[int]): The ID of a specific content item to update. Defaults to None.
            content_meta (Optional[Dict[str, Any]]): Updated metadata for a specific content,
                including available formats and content URL. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: Updated resource metadata if the resource and/or content ID
            exists, otherwise None.

        Structure:
            {
                "basic_meta": {  # System-managed metadata (non-editable by users)
                    "created_at": <ISO timestamp>,
                    "updated_at": <ISO timestamp>,
                    "content_ids": [<int>, ...],  # List of associated content IDs
                    "contents": [<content_meta>, ...],  # List of content metadata
                },
                "detail_meta": {  # User-editable metadata
                    "title": <str>,
                    "description": <str>,
                    "author": <str>,
                    "publishedDate": <str>,
                    "publisher": <str>,
                    "isbn": <str>,
                    "cover_image_url": <str>,
                }
            }
        """
        # Load existing resource metadata
        resource_meta = self.storage_backend.load_resource_meta(
            user_id, self.resource_name, resource_id
        )

        if not resource_meta:
            logging.error(
                f"[_update_resource_meta] error: Metadata of Resource ID {resource_id} not found"
            )
            return None

        existing_basic_meta = resource_meta.get("basic_meta")
        if existing_basic_meta is None:
            logging.error(
                f"[_update_resource_meta] error: Basic metadata of Resource ID {resource_id} not found"
            )
            return None
        existing_detail_meta = resource_meta.get("detail_meta")

        # Update content metadata if content_id is provided
        if content_id is not None:
            existing_contents = existing_basic_meta.get("contents", [])

            # Replace content metadata
            other_contents = [
                content
                for content in existing_contents
                if content.get("id") != content_id
            ]
            if content_meta:
                other_contents.append(content_meta)
            existing_basic_meta["contents"] = other_contents

        # Update detail metadata if provided
        if detail_meta:
            if existing_detail_meta is None:
                existing_detail_meta = detail_meta
            else:
                existing_detail_meta.update(detail_meta)

        existing_basic_meta["content_ids"] = self.content_id_manager.get_content_list(
            user_id, resource_id
        )

        # Update the timestamp of the resource
        now_datetime = datetime.datetime.now(datetime.timezone.utc).isoformat()
        existing_basic_meta["updated_at"] = now_datetime

        resource_meta["basic_meta"] = existing_basic_meta
        resource_meta["detail_meta"] = existing_detail_meta

        return resource_meta

    def _make_content_meta(
        self,
        content_id: int,
        filename: Optional[str],
        mimetype: str,
        content_hash: str,
        extra_info: Optional[ExtraInfo] = None,
        file_size: Optional[int] = None,
    ) -> ContentMeta:
        """
        Creates metadata for a content.

        Args:
            content_id (int): The unique ID of the content.
            filename (str): The original filename of the content.
            mimetype (str): The MIME type of the content.
            content_hash (str): The hash of the content.

        Returns:
            dict: The created content metadata dictionary.

        Structure:
            {
                "id": <int>,
                "filename": <str>,
                "mimetype": <str>,
                "hash": <str>,
                "added_at": <ISO timestamp>,
            }
        """
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        content_meta: ContentMeta = {
            "id": content_id,
            "filename": filename or "Unknown",
            "mimetype": mimetype,  # Removed `extension`, relying on `filename`
            "hash": content_hash,
            "size": file_size,  # Size can be calculated later if needed
            "created_at": created_at,
            "updated_at": created_at,
            "extra_info": extra_info,
        }
        return content_meta

    # Generates a JSON response for the API.
    def _generate_response(
        self,
        status: str,  # Make status required
        message: str,  # Make message required
        resource_id: Optional[str] = None,
        content_id: Optional[int] = None,
        error: Optional[str] = None,
        status_code: int = HTTPStatus.OK,
        basic_meta: Optional[BasicMeta] = None,
        detail_meta: Optional[DetailMeta] = None,
        response_data: Optional[Any] = None,
    ) -> Response:
        """
        Generates a JSON response for the API.

        Args:
            status (str): Response status ("success", "error", "warning", etc.).
            message (str): User-friendly message describing the outcome.
            resource_id (str | None): Optional resource ID.
            content_id (int | None): Optional content ID.
            error (str | None): Optional developer-focused error message (required on error).
            status_code (int): HTTP status code (default: 200).
            data (Any | None): Optional Data Payload

        Returns:
            Response: JSON response and HTTP status code.
        """
        currentframe = inspect.currentframe()
        func_name = (
            currentframe.f_back.f_code.co_name
            if currentframe and currentframe.f_back
            else "unknown"
        )

        response: dict[str, Any] = {
            "status": status,  # Include the response status
            "message": message,  # Include the message in the response
        }

        # If resource_id is provided, add it to the response
        if resource_id is not None:
            response["resource_id"] = resource_id

        # If content_id is provided, add it to the response
        if content_id is not None:
            response["content_id"] = content_id

        # If an error exists, add it to the response
        if error:
            response["error"] = error

        if status == "success":
            if basic_meta is not None:
                response["basic_meta"] = basic_meta
            if detail_meta is not None:
                response["detail_meta"] = detail_meta
            if response_data is not None:
                response["response_data"] = response_data
            logging.info(f"[{func_name}] {message} (status_code={status_code})")

        if status == "warning":
            logging.warning(
                f"[{func_name}] {message} - {error} (status_code={status_code})"
            )
        if status == "error":
            logging.error(
                f"[{func_name}] {message} - {error} (status_code={status_code})",
                exc_info=True,
            )

        # Return the JSON response along with the specified status code
        return make_response(jsonify(response), status_code)

    def _generate_response_dict(
        self,
        response: dict = {},
        status: str = "success",
        message: Optional[str] = None,
        resource_id: Optional[str] = None,
        content_id: Optional[int] = None,
        error: Optional[str] = None,
        status_code: Optional[HTTPStatus] = None,
        data: Optional[dict] = None,
    ):
        currentframe = inspect.currentframe()
        func_name = (
            currentframe.f_back.f_code.co_name
            if currentframe and currentframe.f_back
            else "unknown"
        )
        response = response or {}

        current_status = response.get("status", "unknown")

        # エラーステータスを適切に上書きする
        if current_status != "error":
            if status == "error" or (
                current_status == "warning" and status == "warning"
            ):
                response.update(
                    {
                        "status": status,
                        "message": message,
                        "resource_id": resource_id,
                        "content_id": content_id,
                        "error": error,
                        "status_code": status_code,
                    }
                )
            else:
                response.setdefault("status", status)
                response.setdefault("message", message)
                response.setdefault("resource_id", resource_id)
                response.setdefault("content_id", content_id)
                response.setdefault("error", error)
                response.setdefault("status_code", status_code)
        response["data"] = data

        if status == "success":
            logging.info(f"[{func_name}] {message} (status_code={status_code})")
        elif status == "warning":
            logging.warning(
                f"[{func_name}] {message} - {error} (status_code={status_code})"
            )
        else:
            logging.error(
                f"[{func_name}] {message} - {error} (status_code={status_code})",
                exc_info=True,
            )

        return response

    def _sort_resources(
        self, user_id: str, sort_order: str, sort_field: str
    ) -> List[Dict[str, Any]]:
        reverse = True if sort_order == "desc" else False
        ids = self.resource_id_manager.get_resource_list(user_id)

        def safe_get(meta: Dict[str, Any], field: str, default: Any = "") -> Any:
            value = meta.get(field, default)
            return value if value is not None else default

        try:
            resource_list: List[Dict[str, Any]] = []
            for resource_id in sorted(ids, reverse=reverse):
                resource_meta: Optional[ResourceMeta] = (
                    self.storage_backend.load_resource_meta(
                        user_id, self.resource_name, resource_id
                    )
                )
                if resource_meta:
                    resource_list.append(
                        {
                            "id": resource_id,
                            "basic_meta": resource_meta["basic_meta"],
                            "detail_meta": resource_meta["detail_meta"],
                        }
                    )

            if sort_field == "sorting_date":
                sorted_list = sorted(
                    resource_list,
                    key=lambda x: datetime.datetime.fromisoformat(
                        safe_get(x["detail_meta"], sort_field, "")
                    ),
                    reverse=reverse,
                )
            elif sort_field == "sorting_string":
                sorted_list = sorted(
                    resource_list,
                    key=lambda x: safe_get(x["detail_meta"], sort_field, ""),
                    reverse=reverse,
                )
            elif sort_field in ["created_at", "updated_at"]:
                sorted_list = sorted(
                    resource_list,
                    key=lambda x: datetime.datetime.fromisoformat(
                        safe_get(x["basic_meta"], sort_field, "")
                    ),
                    reverse=reverse,
                )
            elif sort_field == "filename":
                sorted_list = sorted(
                    resource_list,
                    key=lambda x: safe_get(
                        x["basic_meta"]["contents"][0].filename, sort_field, ""
                    ),
                    reverse=reverse,
                )
            else:
                sorted_list = resource_list

            return sorted_list

        except Exception as e:
            logging.error(f"[_sort_resources] error: sort error {e}")
            return resource_list

    def _generate_thumbnail(self, thumbnail_source: bytes, size: str):
        width, height = THUMBNAIL_SIZES[size]
        try:
            with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp:
                image_processor.convert_image(
                    BytesIO(thumbnail_source),
                    tmp.name,
                    "WEBP",
                    width,
                    height,
                    85,
                    ImageFitMode.COVER,
                )
                with open(tmp.name, "rb") as f:
                    return f.read()
        except Exception as e:
            logging.error(
                f"[_generate_thumbnail] error: generate thumbnail failed. ({e})"
            )
        finally:
            os.remove(tmp.name)

    def get_resource_ids(self) -> Response:
        """
        Retrieves a list of resource IDs for the authenticated user.
        Args:
            None (uses authenticated user context).
        Returns:
            Response: A JSON response containing resource IDs.
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)
        return self._generate_response(
            status="success",
            message="Resource list retrieved successfully.",
            response_data={
                "resource_ids": self.resource_id_manager.get_resource_list(user_id)
            },
            status_code=HTTPStatus.OK,
        )

    def get_resource_summary(self) -> Response:
        user_id: str = get_user_id(g.user_info, g.auth_provider)
        resource_count = self.resource_id_manager.count_resources(user_id)
        resource_ids = self.resource_id_manager.get_resource_list(user_id)
        content_count = 0
        for id in resource_ids:
            content_count += len(self.content_id_manager.get_content_list(user_id, id))

        return self._generate_response(
            status="success",
            message="Resources summary retrieved successfully.",
            response_data={
                "resource_count": resource_count,
                "content_count": content_count,
            },
            status_code=HTTPStatus.OK,
        )

    # リソース一覧取得
    # [GET] /RESOURCE_TYPE/
    # Retrieves a paginated list of resource IDs for the authenticated user.
    def get_resource_list(self) -> Response:
        """
        [GET] /RESOURCE_TYPE/
        Retrieves a list of resource IDs belonging to the authenticated user.
        If pagination (`page` and `per_page`) is specified, returns a paginated response.

        Args:
            None (uses authenticated user context).

        Query Parameters:
            page (int, optional): The page number for pagination.
            per_page (int, optional): The number of resources per page.

        Returns:
            Response: A JSON response containing resource IDs and pagination details.

        Process:
            1. Retrieve total number of resources and resource list.
            2. Apply pagination if `page` and `per_page` are provided.
            3. Return a structured response with paginated resource IDs.

        Response Structure:
            {
                "status": "success",
                "message": "Resource list retrieved successfully.",
                "response_data": {
                    "resources": [],
                    "total_items": <int>,
                    "page": <int | "all">,
                    "per_page": <int | "all">
                }
            }
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)
        page: Optional[int] = request.args.get("page", type=int)
        per_page: Optional[int] = request.args.get("per_page", type=int)
        sort_order: Optional[str] = request.args.get("order", "desc")
        sort_field: Optional[str] = request.args.get("sort", "id")

        total_items: int = self.resource_id_manager.count_resources(user_id)

        if not sort_order in ["asc", "desc"]:
            return self._generate_response(
                status="error",
                message="Invalid sort order parameter",
                status_code=HTTPStatus.BAD_REQUEST,
            )

        if not sort_field in [
            "id",
            "created_at",
            "updated_at",
            "filename",
            "size",
            "sorting_string",
            "sorting_date",
        ]:
            return self._generate_response(
                status="error",
                message="Invalid sorting field parameter",
                status_code=HTTPStatus.BAD_REQUEST,
            )

        resource_list: List[Dict[str, Any]] = self._sort_resources(
            user_id, sort_order, sort_field
        )

        start = 0
        end = total_items

        # Apply pagination if page and per_page are specified
        if page is not None and per_page is not None:
            if page < 1 or per_page < 1:
                return self._generate_response(
                    status="error",
                    message="Invalid pagination parameters.",
                    error="Page and per_page must be positive integers.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            start: int = (page - 1) * per_page
            end: int = min(start + per_page, total_items)

            if start >= total_items:
                return self._generate_response(
                    status="error",
                    message="Requested page is out of range.",
                    error=f"Page {page} exceeds the total number of items: {total_items}",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

        response_data = {
            "resources": resource_list[start:end],
            "total_items": total_items,
            "page": page if page is not None else "all",
            "per_page": per_page if per_page is not None else "all",
        }

        return self._generate_response(
            status="success",
            message="Resource list retrieved successfully.",
            response_data=response_data,
            status_code=HTTPStatus.OK,
        )

    # リソース種別特有のコンテンツ変換
    # Handles optional content conversion based on resource type.
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
        return {
            "status": "success",
            "message": "Resource content retrieved and processed successfully.",
            "resource_id": resource_id,
            "content_id": content_id,
            "error": None,
            "status_code": HTTPStatus.OK,
            "data": {"content": base_content, "mimetype": base_mimetype},
        }

    def _validate_resource_id(self, user_id: str, resource_id: str) -> Response:
        """Validate resource ID"""
        if not resource_id:
            return self._generate_response(
                status="error",
                message="Resource ID is required.",
                error="Resource ID not provided in the request path.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if not self.resource_id_manager.exist_resource(user_id, resource_id):
            return self._generate_response(
                status="error",
                message="Resource not found.",
                error=f"Resource ID '{resource_id}' not found",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return make_response(jsonify("success"), HTTPStatus.OK)

    def _validate_content_id(
        self, user_id: str, resource_id: str, content_id: int
    ) -> Response:
        # Validate content ID
        if content_id is None:
            return self._generate_response(
                status="error",
                message="Content ID is required.",
                error="Content ID not provided in the request path",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        try:
            content_id = int(content_id)
        except ValueError:
            return self._generate_response(
                status="error",
                message="Invalid Content ID format.",
                error="Content ID must be an integer",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if not self.content_id_manager.exist_content(user_id, resource_id, content_id):
            return self._generate_response(
                status="error",
                message="Content not found.",
                error=f"Content ID '{content_id}' not found for resource '{resource_id}'",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return make_response(jsonify("success"), HTTPStatus.OK)

    def get_content_list(self, resource_id: str) -> Response:
        """
        Retrieves the list of content IDs and metadata associated with a specific resource.

        Args:
            resource_id (str): The unique identifier for the resource.

        Returns:
            Response: A JSON response containing content IDs and metadata.

        Process:
            1. Validate the resource ID.
            2. Retrieve associated content IDs from the content manager.
            3. Load resource metadata from storage backend.
            4. Return a structured response containing `content_ids` and `contents`.

        Response Structure:
        ```json
        {
            "status": "success",
            "message": "Content list for resource retrieved successfully.",
            "resource_id": "<str>",
            "response_data": {
                "content_ids": [1, 2, ...],
                "contents": [{ "id": <int>, "filename": "<str>", "mimetype": "<str>", "hash": "<str>" }, ...]
            }
        }
        ```
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)

        # Apply user-specific lock (optional for read operations)
        user_lock = self._get_user_lock(user_id)
        with user_lock:
            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Retrieve content IDs
            content_ids = self.content_id_manager.get_content_list(user_id, resource_id)
            if not content_ids:
                return self._generate_response(
                    status="success",
                    message=f"Content list for resource '{resource_id}' retrieved successfully.",
                    resource_id=resource_id,
                    response_data={"content_ids": [], "contents": []},
                )

            # Load resource metadata
            resource_meta = self.storage_backend.load_resource_meta(
                user_id, self.resource_name, resource_id
            )
            if not resource_meta:
                return self._generate_response(
                    status="error",
                    message=f"Resource with ID '{resource_id}' not found.",
                    error=f"Metadata of Resource({resource_id}) not found.",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Extract content metadata
            basic_meta = resource_meta.get("basic_meta")
            if not basic_meta:
                return self._generate_response(
                    status="error",
                    message=f"Resource with ID '{resource_id}' not found.",
                    error=f"Basic metadata of Resource({resource_id}) not found.",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            contents = basic_meta.get("contents", [])

            return self._generate_response(
                status="success",
                message=f"Content list for resource '{resource_id}' retrieved successfully.",
                resource_id=resource_id,
                response_data={"content_ids": content_ids, "contents": contents},
            )

    def _send_file_response(
        self, content: bytes, mimetype: str, filename: str
    ) -> Response:
        """
        Sends a file response with the specified content, MIME type, and filename.
        Args:
            content (bytes): The binary content of the file.
            mimetype (str): The MIME type of the file.
            filename (str): The name of the file to be sent.
        Returns:
            Response: A Flask response object containing the file content.
        """
        response = Response(content, mimetype=mimetype, status=HTTPStatus.OK)

        # ダウンロードが必要なフォーマットは `attachment`
        if mimetype in [
            "application/zip",
            "application/epub+zip",
            "application/x-msdownload",
        ]:
            response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        else:
            response.headers["Content-Disposition"] = f"inline; filename={filename}"
        return response

    # リソース種別特有の thumbnail 生成オプションがあるリソース種別では本メソッドをオバーライドする
    def _optional_thumbnail_process(
        self,
        content_id: Optional[int] = None,
        resource_meta: Optional[ResourceMeta] = None,
        content_buffer: Optional[BytesIO] = None,
    ) -> Optional[BytesIO]:
        """
        Provides resource-specific thumbnail processing options.
        This method should be overridden for resource types requiring special thumbnail generation.

        Args:
            detail_meta (Optional[dict]): Resource-specific metadata, if applicable.
            content_buffer (Optional[BytesIO]): The binary content used for thumbnail generation.

        Returns:
            Optional[BytesIO]: Processed thumbnail data if applicable, otherwise `None`.

        Process:
            1. Resource types requiring special thumbnail processing should override this method.
            2. By default, this method returns `None`, indicating no special processing.
        """
        return None

    def _update_exif_if_possible(self, file: FileStorage, meta: ResourceMeta) -> None:
        """
        Update EXIF data in the provided meta if possible.
        This version uses synchronous geopy and does not require async/await.
        """

        basic_meta = meta.get("basic_meta")
        if isinstance(basic_meta, dict) and "contents" in basic_meta:
            content_meta = basic_meta["contents"][0]
            if isinstance(content_meta, dict):
                content_extra_info = content_meta.get("extra_info")
                basic_meta["extra_info"] = content_extra_info

    def _optional_presave_process(
        self,
        user_id: str,
        resource_id: str,
        resource_meta: Optional[ResourceMeta] = None,
        content_id: Optional[int] = None,
        content_file: Optional[FileStorage] = None,
        thumbnail_file: Optional[Union[FileStorage, BytesIO]] = None,
        content_buffer: Optional[BytesIO] = None,
        thumbnail_buffer: Optional[BytesIO] = None,
        auto_thumbnail: bool = False,
        auto_exif: bool = False,
    ) -> Tuple[Optional[BytesIO], Optional[ResourceMeta], Optional[str]]:
        """
        Placeholder for optional resource creation process.
        This method can be overridden in subclasses to implement specific resource creation logic.
        """

        if auto_exif and content_file and resource_meta:
            self._update_exif_if_possible(content_file, resource_meta)

        if (
            auto_thumbnail
            and not thumbnail_buffer
            and not self.storage_backend.exist_thumbnail(
                user_id, self.resource_name, resource_id, "original"
            )
        ):
            thumbnail_buffer = self._optional_thumbnail_process(
                content_id, resource_meta, content_buffer
            )

        return thumbnail_buffer, resource_meta, None

    def _save_resource(
        self,
        user_id: str,
        resource_id: str,
        resource_meta: Optional[ResourceMeta] = None,
        content_id: Optional[int] = None,
        content_file: Optional[FileStorage] = None,
        thumbnail_file: Optional[Union[FileStorage, BytesIO]] = None,
        content_buffer: Optional[BytesIO] = None,
        thumbnail_buffer: Optional[BytesIO] = None,
        auto_thumbnail: bool = False,
        auto_exif: bool = False,
    ) -> bool:
        """
        Saves the resource to the storage backend.
        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The ID of the resource to save.
            resource_meta (Dict[str, Any]): The metadata of the resource.
            content_buffer (Optional[BytesIO]): The binary content of the resource.
            content_id (Optional[int]): The ID of the content item.
            thumbnail_buffer (Optional[BytesIO]): The thumbnail image buffer.
        Returns:
            bool: True if the resource was saved successfully, False otherwise.
        """
        thumbnail_buffer, resource_meta, error = self._optional_presave_process(
            user_id,
            resource_id,
            resource_meta,
            content_id,
            content_file,
            thumbnail_file,
            content_buffer,
            thumbnail_buffer,
            auto_thumbnail,
            auto_exif,
        )
        if error:
            logging.error(f"[_save_resource] error: {error}")
            return False
        success = self.storage_backend.save_resource(
            user_id=user_id,
            resource_type=self.resource_name,
            resource_id=resource_id,
            metadata=resource_meta,
            content_file=content_buffer,
            content_id=content_id,
            thumbnail_file=thumbnail_buffer,
        )
        return True if success else False

    # 新規リソースの作成
    # [POST] /RESOURCE_TYPE
    # [POST] /RESOURCE_TYPE/detail
    # [POST] /RESOURCE_TYPE/content
    # Creates a new resource (metadata and/or content).
    def make_resource(self, resource_component: Optional[str] = None) -> Response:
        """
        [POST] /RESOURCE_TYPE/
        Creates a new resource. Accepts metadata via 'detail-file' and/or content via 'content-file'.
        The 'resource_component' parameter can specify if only metadata or content is being uploaded.

        Args:
            resource_component (Optional[str]): Specifies if "meta" (metadata-only) or "content" (content-only) is being uploaded. Defaults to None.

        Returns:
            Response: A JSON response indicating the success or failure of the resource creation.

        Process:
            1. Validate input files (metadata and/or content).
            2. Generate resource ID if needed.
            3. Process content file (generate content ID, compute hash, and validate format).
            4. Structure metadata using `_make_resource_meta()`.
            5. Save resource and return a success or error response.

        Response Structure:
            {
                "status": "success",
                "message": "Resource added successfully.",
                "resource_id": "<str>",
                "content_id": "<str>",
            }
        """
        logging.info("[make_resource] Resource creation process started.")
        user_id: str = get_user_id(g.user_info, g.auth_provider)
        user_lock = self._get_user_lock(user_id)

        with user_lock:
            resource_id: Optional[str] = None
            content_id: Optional[int] = None
            content_buffer: Optional[BytesIO] = None
            thumbnail_buffer: Optional[BytesIO] = None
            content_meta: Optional[ContentMeta] = None
            detail_meta: DetailMeta = cast(DetailMeta, {})  # Initialize detail_meta

            # Extract files from request
            detail_file = request.files.get("detail-file", None)
            content_file = request.files.get("content-file", None)
            thumbnail_file = request.files.get("thumbnail-file", None)

            # auto generate thumbnail request
            auto_thumbnail: bool = request.args.get(
                "auto-thumbnail", ""
            ).strip().lower() in [
                "true",
                "yes",
                "1",
            ]
            # auto extract exif request
            auto_exif: bool = request.args.get("auto-exif", "").strip().lower() in [
                "true",
                "yes",
                "1",
            ]

            # Process detail metadata file
            if detail_file:
                try:
                    detail_meta_str = detail_file.read().decode("utf-8")
                    detail_meta = json.loads(detail_meta_str)
                except Exception as e:
                    return self._generate_response(
                        status="error",
                        message="Invalid detail file format.",
                        error=f"Invalid detail-file JSON: {e}",
                        status_code=HTTPStatus.BAD_REQUEST,
                    )
                if not detail_meta or not isinstance(detail_meta, dict):
                    return self._generate_response(
                        status="error",
                        message="Invalid metadata format.",
                        error="Metadata must be a valid JSON object",
                        status_code=HTTPStatus.BAD_REQUEST,
                    )

            # Ensure correct resource creation conditions
            if resource_component == "meta" and not detail_meta:
                return self._generate_response(
                    status="error",
                    message="Metadata is required for this operation.",
                    error="Missing metadata",
                    status_code=HTTPStatus.BAD_REQUEST,
                )
            if resource_component == "content" and not content_file:
                return self._generate_response(
                    status="error",
                    message="Content file is required for this operation.",
                    error="Missing content file",
                    status_code=HTTPStatus.BAD_REQUEST,
                )
            if not resource_component and not detail_meta and not content_file:
                return self._generate_response(
                    status="error",
                    message="Either metadata or a content file is required.",
                    error="Neither metadata nor content file was provided",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Validate thumbnail file
            if thumbnail_file:
                validation_result = self._validate_content_format(
                    "images", thumbnail_file
                )
                if not validation_result:
                    return self._generate_response(
                        status="error",
                        message="Invalid thumbnail format.",
                        error="Invalid thumbnail format or missing file",
                        status_code=HTTPStatus.BAD_REQUEST,
                    )
                (
                    thumbnail_mimetype,
                    thumbnail_filename,
                    thumbnail_extension,
                    thumbnail_buffer,
                ) = validation_result

            # Generate resource ID (required even if only content is provided)
            resource_id = self.resource_id_manager.generate_resource_id(user_id)

            # Process content file (if provided)
            if content_file:
                validation_result = self._validate_content_format(
                    self.resource_name, content_file
                )
                if not validation_result:
                    self.resource_id_manager.release_resource_id(user_id, resource_id)
                    return self._generate_response(
                        status="error",
                        message="Invalid content file format.",
                        error="Invalid content format or missing file",
                        status_code=HTTPStatus.BAD_REQUEST,
                    )
                mimetype, filename, extension, content_buffer = validation_result
                content_hash = hashlib.sha256(content_buffer.getvalue()).hexdigest()
                extra_info: ExtraInfo
                if auto_exif:
                    exif = image_processor.extract_exif(content_file, mimetype)
                    if exif:
                        extra_info = {
                            "exif": exif,
                        }
                        if "GPSLatitude" in exif and "GPSLongitude" in exif:
                            geolocator = Nominatim(user_agent="Memories")
                            location = geolocator.reverse(
                                f"{exif['GPSLatitude']}, {exif['GPSLongitude']}", language="en-US"  # type: ignore
                            )
                            location = cast(Location, location)

                            extra_info["location"] = {
                                "address_string": (
                                    location.address if location else None
                                ),
                                "address": (
                                    location.raw.get("address", {})
                                    if location
                                    else None
                                ),
                            }
                            logging.debug(
                                "address_string: %s",
                                extra_info["location"]["address_string"],
                            )
                            logging.debug(
                                "address: %s", location.address if location else None
                            )
                content_id = self.content_id_manager.generate_content_id(
                    user_id, resource_id
                )

                # Prepare metadata related to the content
                content_meta = self._make_content_meta(
                    content_id,
                    filename,
                    mimetype,
                    content_hash,
                    extra_info,
                    content_file.content_length,
                )

            # Create structured resource metadata
            resource_meta = self._make_resource_meta(
                detail_meta=detail_meta,
                content_id=content_id,
                content_meta=content_meta,
            )

            # Save resource
            success = self._save_resource(
                user_id=user_id,
                resource_id=resource_id,
                resource_meta=resource_meta,
                content_id=content_id,
                content_file=content_file,
                thumbnail_file=thumbnail_file,
                content_buffer=content_buffer,
                thumbnail_buffer=thumbnail_buffer,
                auto_thumbnail=auto_thumbnail,
                auto_exif=auto_exif,
            )

            if not success:
                if content_id is not None:
                    self.content_id_manager.release_content_id(
                        user_id, resource_id, content_id
                    )
                self.resource_id_manager.release_resource_id(user_id, resource_id)
                return self._generate_response(
                    status="error",
                    message="Failed to create the resource.",
                    error="Resource could not be stored due to an internal issue",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return self._generate_response(
                status="success",
                message=f"{self.resource_name} added successfully.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.CREATED,
            )

    # 指定したリソースにコンテンツを追加
    # [POST] /RESOURCE_TYPE/<resource_id>/content
    # Adds new content to an existing resource while ensuring uniqueness.
    def post_resource_content_addition(self, resource_id: str) -> Response:
        """
        [POST] /RESOURCE_TYPE/<resource_id>/content
        Adds new content to an existing resource while ensuring that duplicate content is not stored.
        Content will only be added if its hash differs from any existing content, preventing redundancy.

        Args:
            resource_id (str): The ID of the resource to which the content will be added.

        Returns:
            Response: A JSON response indicating success or failure.

        Process:
            1. Validate resource ID and content file.
            2. Retrieve existing resource metadata.
            3. Compute hash of the new content.
            4. Check for duplicate content (same hash, regardless of extension).
            5. If unique, generate a new content ID and update metadata.
            6. Save updated resource metadata and content file.
            7. Return a success or error response.

        Response Structure:
            {
                "status": "success",
                "message": "New content added successfully.",
                "resource_id": "<str>",
                "content_id": "<str>",
            }
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)
        user_lock = self._get_user_lock(user_id)

        with user_lock:
            # auto extract exif request
            auto_exif: bool = request.args.get("auto-exif", "").strip().lower() in [
                "true",
                "yes",
                "1",
            ]

            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                logging.error(
                    f"[post_resource_content_addition] error: Invalid resource id:{response}"
                )
                return response

            # Retrieve uploaded content file
            content_file = request.files.get("content-file")
            if not content_file:
                return self._generate_response(
                    status="error",
                    message="Content file is required.",
                    error="Missing content file in the request",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Validate content file format
            validation_result = self._validate_content_format(
                self.resource_name, content_file
            )
            if not validation_result:
                return self._generate_response(
                    status="error",
                    message="Invalid content file format or missing file.",
                    error="Content file validation failed",
                    status_code=HTTPStatus.BAD_REQUEST,
                )
            mimetype, filename, _, content_buffer = validation_result

            # Retrieve existing resource metadata
            old_resource_meta = self.storage_backend.load_resource_meta(
                user_id, self.resource_name, resource_id
            )
            if not old_resource_meta:
                return self._generate_response(
                    status="error",
                    message=f"Resource with ID '{resource_id}' not found.",
                    error=f"Metadata of Resource({resource_id}) not found",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Compute hash of the new content
            content_hash = hashlib.sha256(content_buffer.getvalue()).hexdigest()

            # Check for duplicate content based on hash (ignore extension differences)
            same_content = next(
                (
                    content
                    for content in old_resource_meta.get("contents", [])
                    if content.get("hash") == content_hash
                ),
                None,
            )
            if same_content:
                return self._generate_response(
                    status="warning",
                    message="The uploaded content is identical to the existing content.",
                    error="Duplicate content detected. No new content added.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            extra_info: Optional[ExtraInfo] = None
            if auto_exif:
                exif = image_processor.extract_exif(content_file, mimetype)
                if exif:
                    extra_info = {
                        "exif": exif,
                    }
                    if "GPSLatitude" in exif and "GPSLongitude" in exif:
                        geolocator = Nominatim(user_agent="Memories")
                        location = geolocator.reverse(
                            f"{exif['GPSLatitude']}, {exif['GPSLongitude']}", language="en-US"  # type: ignore
                        )
                        location = cast(Location, location)

                        extra_info["location"] = {
                            "address_string": (location.address if location else None),
                            "address": (
                                location.raw.get("address", {}) if location else None
                            ),
                        }
                        logging.debug(
                            "address_string: %s",
                            extra_info["location"]["address_string"],
                        )
                        logging.debug(
                            "address: %s", location.address if location else None
                        )

            # Generate a new content ID for unique content
            content_id = self.content_id_manager.generate_content_id(
                user_id, resource_id
            )

            # Create metadata for the new content
            content_meta = self._make_content_meta(
                content_id,
                filename,
                mimetype,
                content_hash,
                extra_info,
                content_file.content_length,
            )

            # Update resource metadata with new content
            resource_meta = self._update_resource_meta(
                user_id=user_id,
                resource_id=resource_id,
                content_id=content_id,
                content_meta=content_meta,
            )

            if not resource_meta:
                return self._generate_response(
                    status="error",
                    message="Failed to update resource metadata.",
                    error="Resource metadata could not be updated",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            # Save updated metadata and content
            success = self._save_resource(
                user_id=user_id,
                resource_id=resource_id,
                resource_meta=resource_meta,
                content_id=content_id,
                content_file=content_file,
                content_buffer=content_buffer,
            )

            if not success:
                self.content_id_manager.release_content_id(
                    user_id, resource_id, content_id
                )
                return self._generate_response(
                    status="error",
                    message="Failed to add content to the resource.",
                    error="Failed to save the new content to the storage backend",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return self._generate_response(
                status="success",
                message=f"New content added to {self.resource_name} with ID '{resource_id}'.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.CREATED,
            )

    # 指定したリソースのメタ情報取得
    # [GET] /RESOURCE_TYPE/<resource_id>
    # [GET] /RESOURCE_TYPE/<resource_id>/meta
    def get_resource_meta(self, resource_id: str) -> Response:
        """
        [GET] /RESOURCE_TYPE/<resource_id>/meta
        Retrieves metadata for a specific resource, including system-managed (`basic_meta`)
        and user-editable (`detail_meta`) data.

        Args:
            resource_id (str): The ID of the resource whose metadata is being retrieved.

        Returns:
            Response: A JSON response containing the requested resource metadata.

        Process:
            1. Validate resource ID.
            2. Retrieve metadata from the storage backend.
            3. Return a response with `basic_meta` and `detail_meta`.

        Response Structure:
            {
                "status": "success",
                "message": "Metadata retrieved successfully.",
                "resource_id": "<str>",
                "basic_meta": { ... },
                "detail_meta": { ... }
            }
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)
        logging.info(f"get_resource_meta")
        # Apply user-specific lock (optional for read operations)
        user_lock = self._get_user_lock(user_id)
        with user_lock:
            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Retrieve the metadata from storage backend
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
            return self._generate_response(
                status="success",
                message=f"Metadata for resource '{resource_id}' retrieved successfully.",
                resource_id=resource_id,
                basic_meta=resource_meta.get("basic_meta"),
                detail_meta=resource_meta.get("detail_meta"),
            )

    # 指定したコンテントの取得
    # [GET] /RESOURCE_TYPE/<resource_id>/content/<content_id>
    # Retrieves content for a specific resource using `content_id`.
    def get_resource_content(
        self, resource_id: str, content_id: int, filename: Optional[str] = None
    ) -> Response:
        """
        [GET] /RESOURCE_TYPE/<resource_id>/content/<content_id>
        Retrieves content for a specific resource by `content_id`.
        `extension`-based searches have been removed, and MIME type (`mimetype`) is now used for format management.

        Args:
            resource_id (str): The ID of the resource whose content is being retrieved.
            content_id (int): The unique ID of the content associated with the resource.

        Query Parameters:
            binary (bool, optional): If true, returns raw binary data instead of a base64-encoded string.

        Returns:
            Response: Either a JSON response containing a base64-encoded content or raw binary data.

        Process:
            1. Validate resource ID and content ID.
            2. Retrieve content from the storage backend.
            3. Fetch resource metadata and verify `content_id` exists.
            4. Retrieve the MIME type (`mimetype`) of the content.
            5. Apply optional content conversion.
            6. If binary mode is requested, return raw binary data.
            7. Otherwise, encode content in base64 and return a JSON response.

        Response Structure (base64-encoded content):
            {
                "status": "success",
                "message": "Resource content retrieved successfully.",
                "resource_id": "<str>",
                "content_id": "<int>",
                "response_data": {
                    "content": "<base64-encoded string>",
                    "mimetype": "<mime-type>"
                }
            }
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)

        user_lock = self._get_user_lock(user_id)
        with user_lock:
            binary_mode: bool = request.args.get("binary", "").lower().strip() in [
                "true",
                "yes",
                "1",
            ]

            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Validate content ID
            response = self._validate_content_id(user_id, resource_id, content_id)
            if response.status_code != HTTPStatus.OK:
                return response
            content_id = int(content_id)

            # Retrieve content from storage
            base_content = self.storage_backend.load_resource_content(
                user_id, self.resource_name, resource_id, content_id
            )

            if not base_content:
                return self._generate_response(
                    status="error",
                    message="Content not found.",
                    error=f"Content (content_id:{content_id}) not found for resource {resource_id}",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Retrieve resource metadata
            resource_meta = self.storage_backend.load_resource_meta(
                user_id, self.resource_name, resource_id
            )

            if resource_meta is None:
                return self._generate_response(
                    status="error",
                    message="Metadata for the resource not found.",
                    error=f"Metadata for resource ID {resource_id} not found.",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Find `content_meta` matching `content_id`
            basic_meta = resource_meta.get("basic_meta", cast(BasicMeta, {})) or cast(
                BasicMeta, {}
            )
            content_meta_list = basic_meta.get("contents", [])
            matched_content = next(
                (
                    content
                    for content in content_meta_list
                    if content.get("id") == int(content_id)
                ),
                None,
            )

            if matched_content is None:
                return self._generate_response(
                    status="error",
                    message=f"Content with ID '{content_id}' not found in resource metadata.",
                    error=f"Content ID {content_id} is missing from resource metadata.",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Get MIME type
            mimetype = (
                matched_content.get("mimetype", "application/octet-stream")
                .strip()
                .lower()
            )

            # Apply optional content conversion
            response = self._optional_content_convert(
                resource_id, content_id, base_content, mimetype
            )
            if not response:
                return self._generate_response(
                    status="error",
                    message="Internal Server Error.",
                    error=f"Unknown internal error occurred. {self.resource_name}_optional_content_convert()",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            if response["status"] == "error":
                return self._generate_response(
                    response["status"],
                    response["message"],
                    response["resource_id"],
                    response["content_id"],
                    response["error"],
                    response["status_code"],
                )
            content = response["data"].get("content", None)
            mimetype = response["data"].get("mimetype", "application/octet-stream")
            extension = FULL_FILETYPE_MAP.get(mimetype, "bin")

            if filename:
                logging.info("[get_resource_content] Returning file")
                return send_file(
                    BytesIO(content), mimetype=mimetype, download_name=filename
                )

            # Return binary content if requested
            if binary_mode:
                logging.info("[get_resource_content] Returning raw binary content")
                return Response(content, mimetype=mimetype, status=HTTPStatus.OK)

                # return self._send_file_response(
                #     content, mimetype, f"content.{extension}"
                # )

            # Encode content in base64 and return JSON response
            content_encoded = base64.b64encode(content).decode("utf-8")
            return self._generate_response(
                status="success",
                message="Resource content retrieved successfully.",
                resource_id=resource_id,
                content_id=content_id,
                response_data={"content": content_encoded, "mimetype": mimetype},
                status_code=HTTPStatus.OK,
            )

    # 指定したリソースのサムネイル取得
    # [GET] /RESOURCE_TYPE/<resource_id>/thumbnail
    # Retrieves the thumbnail for a specific resource.
    def get_resource_thumbnail(self, resource_id: str) -> Response:
        """
        [GET] /RESOURCE_TYPE/<resource_id>/thumbnail
        Retrieves the thumbnail for a specific resource.

        Args:
            resource_id (str): The ID of the resource whose thumbnail is being retrieved.

        Query Parameters:
            thumbnail_size (str, optional): Specifies the size of the thumbnail. Defaults to "medium".
                Available sizes: ["original", "small", "medium", "large"].
            binary (bool, optional): If true, returns raw binary data instead of a base64-encoded string.

        Returns:
            Response: Either a JSON response containing a base64-encoded thumbnail or raw binary data.

        Process:
            1. Validate resource ID.
            2. Parse query parameters (`thumbnail_size` and `binary`).
            3. Retrieve the requested thumbnail from the storage backend.
            4. If binary mode is requested, return raw binary data.
            5. Otherwise, encode thumbnail in base64 and return a JSON response.

        Response Structure (base64-encoded thumbnail):
            {
                "status": "success",
                "message": "Thumbnail retrieved successfully.",
                "resource_id": "<str>",
                "response_data": {
                    "thumbnail": "<base64-encoded string>"
                }
            }
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)

        # Apply user-specific lock (optional for read operations)
        user_lock = self._get_user_lock(user_id)
        with user_lock:
            # Parse query parameters
            thumbnail_size: str = request.args.get("size", "medium").strip().lower()
            binary_mode: bool = request.args.get("binary", "").strip().lower() in [
                "true",
                "yes",
                "1",
            ]

            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Validate thumbnail size parameter
            if thumbnail_size not in ["original", "small", "medium", "large"]:
                return self._generate_response(
                    status="error",
                    message="Invalid thumbnail size parameter.",
                    error=f"'{thumbnail_size}' is not a valid thumbnail size",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Retrieve thumbnail from storage
            thumbnail = self.storage_backend.load_resource_thumbnail(
                user_id, self.resource_name, resource_id, thumbnail_size
            )
            if thumbnail is None and thumbnail_size != "original":
                thumbnail_original = self.storage_backend.load_resource_thumbnail(
                    user_id, self.resource_name, resource_id, "original"
                )
                if thumbnail_original:
                    thumbnail = self._generate_thumbnail(
                        thumbnail_original, thumbnail_size
                    )
                    if thumbnail:
                        self.storage_backend.save_thumbnail(
                            user_id,
                            self.resource_name,
                            resource_id,
                            thumbnail,
                            thumbnail_size,
                        )

            if thumbnail is None:
                return self._generate_response(
                    status="error",
                    message="Thumbnail not found.",
                    error=f"No thumbnail available for resource {resource_id} with size '{thumbnail_size}'",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Return binary thumbnail if requested
            if binary_mode:
                logging.info("[get_resource_thumbnail] Returning raw binary thumbnail")
                return Response(thumbnail, mimetype="image/webp", status=HTTPStatus.OK)

            # Encode thumbnail in base64 and return JSON response
            thumbnail_encoded = base64.b64encode(thumbnail).decode("utf-8")
            return self._generate_response(
                status="success",
                message=f"Thumbnail for resource '{resource_id}' retrieved successfully.",
                resource_id=resource_id,
                response_data={"thumbnail": thumbnail_encoded},
                status_code=HTTPStatus.OK,
            )

    # 指定したリソースの詳細情報更新
    # [PUT] /RESOURCE_TYPE/<resource_id>
    # [PUT] /RESOURCE_TYPE/<resource_id>/detail
    # Updates the `detail_meta` for an existing resource.
    def put_resource_detail(self, resource_id: str) -> Response:
        """
        [PUT] /RESOURCE_TYPE/<resource_id>/detail
        Updates only the `detail_meta` for an existing resource.

        Args:
            resource_id (str): The ID of the resource whose metadata is being updated.

        Request:
            - Requires a JSON file (`detail-file`) containing the updated metadata.

        Returns:
            Response: A JSON response indicating success or failure.

        Process:
            1. Validate resource ID and check for `detail-file`.
            2. Parse and validate the JSON metadata.
            3. Update only `detail_meta`, ensuring `basic_meta` remains unchanged.
            4. Save the updated resource metadata to storage.
            5. Return a success or error response.

        Response Structure:
            {
                "status": "success",
                "message": "Details updated successfully.",
                "resource_id": "<str>",
            }
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)

        user_lock = self._get_user_lock(user_id)  # Apply user-specific lock
        with user_lock:
            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Validate detail file existence
            detail_file = request.files.get("detail-file")
            if detail_file is None:
                return self._generate_response(
                    status="error",
                    message="Detail file is required.",
                    error="Missing 'detail-file' in the request",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Parse detail metadata
            try:
                detail_meta_str = detail_file.read().decode("utf-8")
                detail_meta = json.loads(detail_meta_str)
            except Exception as e:
                return self._generate_response(
                    status="error",
                    message="Invalid detail file format.",
                    error=f"Invalid detail-file JSON: {e}",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Update only `detail_meta`, ensuring `basic_meta` remains unchanged
            resource_meta = self._update_resource_meta(
                user_id, resource_id, detail_meta
            )
            if not resource_meta:
                return self._generate_response(
                    status="error",
                    message=f"Resource with ID '{resource_id}' not found.",
                    error=f"Resource metadata for ID({resource_id}) not found.",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Save the updated metadata
            success = self.storage_backend.save_resource(
                user_id=user_id,
                resource_type=self.resource_name,
                resource_id=resource_id,
                metadata=resource_meta,
            )

            if not success:
                return self._generate_response(
                    status="error",
                    message="Failed to update resource details.",
                    error="Failed to save the updated resource metadata",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return self._generate_response(
                status="success",
                message=f"Details for {self.resource_name} with ID '{resource_id}' updated successfully.",
                resource_id=resource_id,
                status_code=HTTPStatus.OK,
            )

    # 指定したコンテンツのコンテンツ更新
    # Updates existing content for a given resource while preventing duplicate content.
    def put_resource_content(self, resource_id: str, content_id: int) -> Response:
        """
        [PUT] /RESOURCE_TYPE/<resource_id>/content/<content_id>
        Updates existing content in a resource while ensuring that identical content does not get duplicated.

        Args:
            resource_id (str): The ID of the resource whose content is being updated.
            content_id (int): The ID of the content within the resource.

        Request:
            - Requires a content file (`content-file`) for updating the content.
            - Optional: `generate-thumbnail=true` triggers thumbnail generation.

        Returns:
            Response: A JSON response indicating success or failure.

        Process:
            1. Validate resource ID and content ID.
            2. Ensure the resource and content exist.
            3. Validate and process uploaded content.
            4. Check for duplicate content by comparing hashes.
            5. Update resource metadata and prevent redundant storage.
            6. Save updated resource and return a success response.

        Response Structure:
            {
                "status": "success",
                "message": "Content updated successfully.",
                "resource_id": "<str>",
                "content_id": "<int>",
            }
        """
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

            # Validate content file existence
            content_file = request.files.get("content-file")
            if content_file is None:
                return self._generate_response(
                    status="error",
                    message="Content file is required.",
                    error="Missing 'content-file' in the request",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Validate content format
            validation_result = self._validate_content_format(
                self.resource_name, content_file
            )
            if not validation_result:
                return self._generate_response(
                    status="error",
                    message="Invalid content file format.",
                    error="Invalid content format or missing file",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            mimetype, filename, _, content_buffer = validation_result

            # Compute hash for duplicate check
            content_hash = hashlib.sha256(content_buffer.getvalue()).hexdigest()
            resource_meta = self.storage_backend.load_resource_meta(
                user_id, self.resource_name, resource_id
            )
            if not resource_meta:
                return self._generate_response(
                    status="error",
                    message="Resource metadata not found.",
                    error=f"Resource metadata for ID {resource_id} not found",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Check for duplicate content
            content_meta_list = resource_meta.get("contents", [])
            matched_content = next(
                (
                    content
                    for content in content_meta_list
                    if content.get("hash") == content_hash
                ),
                None,
            )

            if matched_content:
                return self._generate_response(
                    status="warning",
                    message="The uploaded content is identical to the existing content.",
                    error="Duplicate content detected.",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Create metadata for updated content
            content_meta = self._make_content_meta(
                content_id,
                filename,
                mimetype,
                content_hash,
                None,
                content_file.content_length,
            )

            # Update resource metadata
            resource_meta = self._update_resource_meta(
                user_id=user_id,
                resource_id=resource_id,
                content_id=content_id,
                content_meta=content_meta,
            )
            if not resource_meta:
                return self._generate_response(
                    status="error",
                    message="Failed to update resource metadata.",
                    error=f"Metadata for Resource ID({resource_id}) or Content ID({content_id}) not found",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Save updated resource
            success = self._save_resource(
                user_id=user_id,
                resource_id=resource_id,
                resource_meta=resource_meta,
                content_id=content_id,
                content_file=content_file,
                content_buffer=content_buffer,
            )

            if not success:
                return self._generate_response(
                    status="error",
                    message="Failed to update content.",
                    error="Failed to save the updated content to the storage backend",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            return self._generate_response(
                status="success",
                message=f"Content with ID '{content_id}' updated for {self.resource_name} with ID '{resource_id}'.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.OK,
            )

    # 指定したリソースのサムネイル更新
    # [PUT] /RESOURCE_TYPE/<resource_id>/thumbnail
    # Updates the thumbnail for an existing resource while preserving metadata and content.
    def put_resource_thumbnail(self, resource_id: str) -> Response:
        """
        [PUT] /RESOURCE_TYPE/<resource_id>/thumbnail
        Updates the thumbnail for an existing resource without modifying its metadata or content.

        Args:
            resource_id (str): The ID of the resource whose thumbnail is being updated.

        Request:
            - Requires an image file (`thumbnail-file`) for updating the thumbnail.

        Returns:
            Response: A JSON response indicating success or failure.

        Process:
            1. Validate resource ID.
            2. Validate and process uploaded thumbnail file.
            3. Apply content validation (`_validate_content_format()`).
            4. Save updated thumbnail while preserving existing metadata and content.
            5. Return a success or error response.

        Response Structure:
            {
                "status": "success",
                "message": "Thumbnail updated successfully.",
                "resource_id": "<str>",
            }
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)

        user_lock = self._get_user_lock(user_id)
        with user_lock:
            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Validate thumbnail file existence
            thumbnail_file = request.files.get("thumbnail-file")

            if not thumbnail_file:
                return self._generate_response(
                    status="error",
                    message="Thumbnail file is required.",
                    error="Missing 'thumbnail-file' in the request",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Validate thumbnail format
            validation_result = self._validate_content_format("images", thumbnail_file)
            if not validation_result:
                return self._generate_response(
                    status="error",
                    message="Invalid thumbnail format.",
                    error="Invalid thumbnail format or missing file",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            (
                thumbnail_mimetype,
                thumbnail_filename,
                thumbnail_extension,
                thumbnail_buffer,
            ) = validation_result

            # Save updated thumbnail
            success = self._save_resource(
                user_id=user_id,
                resource_id=resource_id,
                thumbnail_file=thumbnail_file,
                thumbnail_buffer=thumbnail_buffer,
            )

            if not success:
                return self._generate_response(
                    status="error",
                    message="Failed to update resource thumbnail.",
                    error="Failed to save the updated thumbnail to the storage backend",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return self._generate_response(
                status="success",
                message=f"Thumbnail for resource '{resource_id}' updated successfully.",
                resource_id=resource_id,
                status_code=HTTPStatus.OK,
            )

    # 指定したリソースのサムネイル部分更新
    # [PATCH] /RESOURCE_TYPE/<resource_id>/thumbnail
    # Rotates an existing resource thumbnail by a specified angle.
    def patch_resource_thumbnail(self, resource_id: str) -> Response:
        """
        [PATCH] /RESOURCE_TYPE/<resource_id>/thumbnail
        Rotates an existing resource thumbnail by a specified angle.

        Args:
            resource_id (str): The ID of the resource whose thumbnail needs rotation.

        Returns:
            Response: `HTTPStatus.OK` if the rotation is successful, or an error response.

        Process:
            1. Validate resource ID.
            2. Ensure the resource exists and has an original thumbnail.
            3. Retrieve and validate the angle parameter.
            4. Rotate the thumbnail image.
            5. Save the updated thumbnail.
            6. Return a `HTTPStatus.OK` response if rotation is successful.

        Response Structure:
            - **Success**: `HTTPStatus.OK`
            - **Failure**: JSON response with error details.
        """

        # Retrieve the user ID from the request data
        user_id: str = get_user_id(g.user_info, g.auth_provider)

        # Acquire a lock for the user to ensure safe concurrent operations
        user_lock = self._get_user_lock(user_id)
        with user_lock:
            # Validate the resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Parse request data and check for the 'angle' parameter
            data = request.json
            if not data or "angle" not in data:
                return self._generate_response(
                    status="error",
                    message="Missing angle parameter",
                    error="Missing angle parameter",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Validate the 'angle' parameter to ensure it's an integer
            try:
                angle = int(data["angle"])
            except ValueError:
                return self._generate_response(
                    status="error",
                    message="Invalid angle parameter",
                    error="Angle must be an integer",
                    status_code=HTTPStatus.BAD_REQUEST,
                )

            # Load the original thumbnail image for the given resource ID
            thumbnail = self.storage_backend.load_resource_thumbnail(
                user_id, self.resource_name, resource_id, "original"
            )
            if not thumbnail:
                return self._generate_response(
                    status="error",
                    message="Thumbnail not found",
                    error="No original thumbnail available",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Rotate the thumbnail image by the specified angle
            rotated_thumbnail = image_processor.rotate_image(thumbnail, angle, "WEBP")
            output = BytesIO(rotated_thumbnail)

            # Save the updated thumbnail image
            success = self._save_resource(
                user_id=user_id,
                resource_id=resource_id,
                thumbnail_file=output,
                thumbnail_buffer=output,
            )

            if not success:
                return self._generate_response(
                    status="error",
                    message="Failed to save thumbnail",
                    error="Failed to save thumbnail",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            # Return a success response indicating the thumbnail has been rotated
            return self._generate_response(
                status="success",
                message=f"Thumbnail rotated by {angle}°",
                resource_id=resource_id,
                status_code=HTTPStatus.OK,
            )

    # 指定したリソースの削除
    # [DELETE] /RESOURCE_TYPE/<resource_id>
    # Deletes a specific resource by `resource_id`.
    def delete_resource(self, resource_id: str) -> Response:
        """
        [DELETE] /RESOURCE_TYPE/<resource_id>
        Deletes an existing resource and removes its metadata and content.

        Args:
            resource_id (str): The ID of the resource to delete.

        Returns:
            Response: `HTTPStatus.NO_CONTENT` if deletion is successful, or an error response.

        Process:
            1. Validate resource ID.
            2. Ensure the resource exists.
            3. Execute resource deletion.
            4. Release the resource ID from resource management.
            5. Return a `HTTPStatus.NO_CONTENT` response if deletion is successful.

        Response Structure:
            - **Success**: `HTTPStatus.NO_CONTENT`
            - **Failure**: JSON response with error details.
        """
        user_id: str = get_user_id(g.user_info, g.auth_provider)

        user_lock = self._get_user_lock(user_id)
        with user_lock:
            # Validate resource ID
            response = self._validate_resource_id(user_id, resource_id)
            if response.status_code != HTTPStatus.OK:
                return response

            # Check if the resource exists
            if not self.resource_id_manager.exist_resource(user_id, resource_id):
                return self._generate_response(
                    status="error",
                    message=f"Resource with ID '{resource_id}' not found.",
                    error=f"Resource {resource_id} not found",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            # Execute resource deletion
            logging.info(f"[delete_resource] Deleting resource: {resource_id}")
            success = self.storage_backend.delete_resource(
                user_id, self.resource_name, resource_id
            )

            if not success:
                return self._generate_response(
                    status="error",
                    message="Failed to delete the resource.",
                    error="Failed to delete resource from storage backend",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            # Release resource ID from manager
            logging.info(
                f"[delete_resource] Resource {resource_id} deleted successfully."
            )
            self.resource_id_manager.release_resource_id(user_id, resource_id)

            return Response(status=HTTPStatus.NO_CONTENT)

    # 指定したコンテンツの削除
    # [DELETE] /RESOURCE_TYPE/<resource_id>/content/<content_id>
    # Deletes a specific content item from a resource while preserving metadata and thumbnail.
    def delete_resource_content(self, resource_id: str, content_id: int) -> Response:
        """
        [DELETE] /RESOURCE_TYPE/<resource_id>/content/<content_id>
        Deletes a specific content item from a resource without affecting metadata or thumbnails.

        Args:
            resource_id (str): The ID of the resource from which content will be deleted.
            content_id (int): The unique ID of the content item to be deleted.

        Returns:
            Response: `HTTPStatus.NO_CONTENT` if deletion is successful, or an error response.

        Process:
            1. Validate resource ID and content ID.
            2. Remove the content from metadata and update `basic_meta`.
            3. Save updated metadata after deletion.
            4. Delete the actual content from storage.
            5. Return `HTTPStatus.NO_CONTENT` if deletion is successful.

        Response Structure:
            - **Success**: `HTTPStatus.NO_CONTENT`
            - **Failure**: JSON response with error details.
        """
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

            # Retrieve and update resource metadata
            updated_resource_meta = self.storage_backend.load_resource_meta(
                user_id, self.resource_name, resource_id
            )
            if not updated_resource_meta:
                return self._generate_response(
                    status="error",
                    message="Failed to retrieve resource metadata.",
                    error="Failed to get resource metadata",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            updated_basic_meta = updated_resource_meta.get(
                "basic_meta", cast(BasicMeta, {})
            ) or cast(BasicMeta, {})
            contents = updated_basic_meta.get("contents", []) or []

            # Remove the content entry from metadata
            existing_content = next(
                (
                    content
                    for content in contents
                    if int(content.get("id")) == content_id
                ),
                None,
            )
            if not existing_content:
                return self._generate_response(
                    status="error",
                    message=f"Content with ID '{content_id}' not found in metadata.",
                    error=f"Content ID {content_id} not found in resource metadata",
                    status_code=HTTPStatus.NOT_FOUND,
                )

            updated_basic_meta["contents"] = [
                content for content in contents if int(content.get("id")) != content_id
            ]
            updated_basic_meta["content_ids"] = [
                cid
                for cid in updated_basic_meta.get("content_ids", [])
                if cid != content_id
            ]
            updated_resource_meta["basic_meta"] = updated_basic_meta

            # Save updated metadata
            try:
                success_meta = self.storage_backend.save_resource_meta(
                    user_id, self.resource_name, resource_id, updated_resource_meta
                )
                if not success_meta:
                    return self._generate_response(
                        status="error",
                        message="Failed to update resource metadata.",
                        error="Failed to update resource metadata",
                        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
            except Exception as e:
                return self._generate_response(
                    status="error",
                    message="Failed to update resource metadata.",
                    error=f"Failed to update resource metadata: {e}",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            # Delete content from storage
            success_content = self.storage_backend.delete_resource_content(
                user_id, self.resource_name, resource_id, content_id
            )
            if not success_content:
                return self._generate_response(
                    status="error",
                    message="Failed to delete the resource content.",
                    error=f"Failed to remove resource content {content_id}",
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            logging.info(
                f"[delete_resource_content] Resource content {content_id} deleted successfully for resource {resource_id}"
            )
            return Response(status=HTTPStatus.NO_CONTENT)

    def patch_content_exif(self, resource_id: str, content_id: int) -> Response:

        return self._generate_response(
            status="error",
            message="patch_content_exif is not suported",
            error="patch_content_exif isNot supported",
            status_code=HTTPStatus.NOT_IMPLEMENTED,
        )
