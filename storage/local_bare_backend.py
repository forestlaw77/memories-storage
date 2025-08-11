# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import asyncio
import datetime
import glob
import hashlib
import json
import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import List, Optional

import aiofiles
from werkzeug.datastructures import FileStorage

from manager.image_processor import image_processor
from models.types import ResourceMeta
from storage.abstract_backend import AbstractStorageBackend


class LocalStorageBareBackend(AbstractStorageBackend):
    def __init__(self, storage_root: str = "local_storage"):
        self.storage_root = storage_root
        os.makedirs(self.storage_root, exist_ok=True)

    def _get_user_dir(self, user_id: str) -> str:
        return os.path.join(self.storage_root, user_id)

    def _get_user_metadata_path(self, user_id: str) -> str:
        return os.path.join(self._get_user_dir(user_id), "metadata.json")

    def load_user_metadata(self, user_id: str) -> Optional[dict]:
        try:
            metadata_path = self._get_user_metadata_path(user_id)
            if not os.path.exists(metadata_path):
                return None

            with open(metadata_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"error: Failed to read user metadata. ({e})")
            return None

    def save_user_metadata(self, user_id: str, metadata: dict) -> bool:
        try:
            user_dir = self._get_user_dir(user_id)
            os.makedirs(user_dir, exist_ok=True)

            with open(self._get_user_metadata_path(user_id), "w") as f:
                json.dump(metadata, f, indent=4)

            return True
        except Exception as e:
            logging.error(f"error: Failed to write user metadata. ({e})")
            return False

    def _update_user_metadata(self, user_id: str, resource_type: str) -> None:
        """Updates the user's metadata with the latest resource modification time."""
        update_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_metadata = self.load_user_metadata(user_id) or {"resources": {}}

        user_metadata["resources"][resource_type] = update_at
        self.save_user_metadata(user_id, user_metadata)

    def _get_resource_type_dir(self, user_id: str, resource_type: str) -> str:
        return os.path.join(self.storage_root, user_id, resource_type)

    def _get_resource_dir(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> str:
        """リソースのディレクトリパスを取得"""
        return os.path.join(
            self._get_resource_type_dir(user_id, resource_type),
            resource_id[-2:],
            resource_id,
        )

    def _get_metadata_path(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> str:
        """メタデータファイルのパスを取得"""
        return os.path.join(
            self._get_resource_dir(user_id, resource_type, resource_id), "metadata.json"
        )

    def _get_content_path(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        content_id: int,
    ) -> str:
        """コンテンツファイルのパスを取得"""
        return os.path.join(
            self._get_resource_dir(user_id, resource_type, resource_id),
            f"content_{content_id}",
        )

    def _get_thumbnail_path(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> tuple[str, str, str, str]:
        """サムネイルファイルのパスを取得"""
        resource_dir = self._get_resource_dir(user_id, resource_type, resource_id)
        return (
            os.path.join(resource_dir, "thumbnail_original.webp"),
            os.path.join(resource_dir, "thumbnail_small.webp"),
            os.path.join(resource_dir, "thumbnail_medium.webp"),
            os.path.join(resource_dir, "thumbnail_large.webp"),
        )

    def get_resource_list(self, user_id: str, resource_type: str) -> List[str]:
        """
        Retrieves a list of resource IDs for a given user and resource type.

        Args:
            user_id (str): The ID of the user who owns the resources.
            resource_type (str): The type of the resource (e.g., 'books', 'documents').

        Returns:
            List[str]: A list of resource IDs found within the specified resource type.

        Process:
            1. Determine the directory for the specified `resource_type`.
            2. Verify if the directory exists. If not, return an empty list.
            3. Traverse the directory structure to locate resources.
            4. Identify directories containing `metadata.json`, extract their names as `resource_id`.
            5. Return the collected resource IDs.
        """
        # Determine resource type directory
        resource_type_dir = self._get_resource_type_dir(user_id, resource_type)

        # Verify directory existence
        if not os.path.exists(resource_type_dir):
            return []

        resource_ids = []

        # Traverse resource directory
        for root, _, files in os.walk(resource_type_dir):
            if "metadata.json" in files:
                # Extract `resource_id` as the final directory name
                resource_id = os.path.basename(root)
                resource_ids.append(resource_id)

        return resource_ids

    def load_resource_meta(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> Optional[dict]:
        """
        Load the metadata for the specified resource.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_type (str): The type of the resource (e.g., 'image', 'video').
            resource_id (str): The unique identifier for the resource.

        Returns:
            Optional[dict]: The metadata dictionary if the file exists, otherwise None.

        Raises:
            RuntimeError: If an error occurs while reading or parsing the metadata file.
        """
        # Construct the path to the metadata file.
        metadata_path = self._get_metadata_path(user_id, resource_type, resource_id)

        # Check if the metadata file exists. If not, return None.
        if not os.path.exists(metadata_path):
            return None

        try:
            # Open and read the metadata file in read mode with UTF-8 encoding.
            with open(metadata_path, "r", encoding="utf-8") as f:
                # Load the JSON data from the file into a Python dictionary.
                metadata = json.load(f)
                # Convert the 'available_formats' list (if it exists and is a list) to a set.
                # Convert the 'content_ids' list (if it exists and is a list) to a set.
                # メタ情報の中身はビジネスロジックに依存するので、ここでは変換しない

                # Return the loaded and processed metadata.
                return metadata
        except Exception as e:
            # If any error occurs during file reading or JSON parsing, raise a RuntimeError.
            raise RuntimeError(f"Failed to load metadata for {resource_id}: {str(e)}")

    def load_resource_content(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        content_id: int,
    ) -> Optional[bytes]:
        """
        Loads the content file for a specified resource.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_type (str): The type of the resource (e.g., 'books', 'documents').
            resource_id (str): The unique identifier for the resource.
            content_id (int): The unique identifier of the content.

        Returns:
            Optional[bytes]: Raw binary content if the file exists, otherwise `None`.

        Process:
            1. Construct the content file path using provided `content_id`.
            2. Check if the file exists before attempting to load.
            3. Load and return the content file, or log an error if retrieval fails.
        """
        # Construct content file path
        content_path = self._get_content_path(
            user_id, resource_type, resource_id, content_id
        )

        # Load file if path is valid
        try:
            with open(content_path, "rb") as f:
                return f.read()
        except Exception as e:
            logging.error(
                f"Failed to load content for {resource_id} ({content_id}): {str(e)}"
            )
            return None

    def load_resource_thumbnail(
        self, user_id: str, resource_type: str, resource_id: str, thumbnail_size: str
    ) -> Optional[bytes]:
        """
        Loads the thumbnail image for a specified resource.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_type (str): The type of the resource (e.g., 'books', 'documents').
            resource_id (str): The unique identifier for the resource.
            thumbnail_size (str): The requested thumbnail size ('original', 'small', 'medium', 'large').

        Returns:
            Optional[bytes]: Raw binary content if the thumbnail exists, otherwise `None`.

        Process:
            1. Determine the correct thumbnail file path based on `thumbnail_size`.
            2. Validate if the requested size is supported (`original`, `small`, `medium`, `large`).
            3. Check if the thumbnail file exists before attempting to load.
            4. Load and return the thumbnail file, or log an error if retrieval fails.
        """
        (
            original_thumbnail_path,
            small_thumbnail_path,
            medium_thumbnail_path,
            large_thumbnail_path,
        ) = self._get_thumbnail_path(user_id, resource_type, resource_id)

        # Validate thumbnail size
        if thumbnail_size not in ["original", "small", "medium", "large"]:
            logging.warning(f"Invalid thumbnail size requested: {thumbnail_size}")
            return None

        # Determine the correct file path
        thumbnail_path_map = {
            "original": original_thumbnail_path,
            "small": small_thumbnail_path,
            "medium": medium_thumbnail_path,
            "large": large_thumbnail_path,
        }
        thumbnail_path = thumbnail_path_map.get(thumbnail_size)

        # Verify file existence
        if not thumbnail_path or not os.path.exists(thumbnail_path):
            logging.warning(f"Thumbnail not found: {thumbnail_path}")
            return None

        # Load file if valid
        try:
            with open(thumbnail_path, "rb") as f:
                return f.read()
        except Exception as e:
            logging.error(f"Failed to load thumbnail for {resource_id}: {str(e)}")
            raise RuntimeError(f"Failed to load thumbnail for {resource_id}: {str(e)}")

    # async def bulk_save_resources(
    #     self,
    #     user_id: str,
    #     resource_type: str,
    #     resources: List[dict],
    #     resource_ids: List[str],
    # ) -> dict:
    #     """Bulk saves multiple resources asynchronously."""

    #     success_list = []
    #     failed_list = []

    #     async def save_single_resource(resource, resource_id):
    #         try:
    #             # ✅ 非同期でメタデータを保存
    #             if "metadata" in resource:
    #                 metadata_path = self._get_metadata_path(
    #                     user_id, resource_type, resource_id
    #                 )
    #                 async with aiofiles.open(metadata_path, "w", encoding="utf-8") as f:
    #                     await f.write(json.dumps(resource["metadata"], indent=4))

    #             # ✅ 非同期でコンテンツを保存
    #             if "content_file" in resource:
    #                 content_path = self._get_content_path(
    #                     user_id, resource_type, resource_id, resource["content_id"]
    #                 )
    #                 async with aiofiles.open(content_path, "wb") as f:
    #                     await f.write(resource["content_file"].getvalue())

    #             success_list.append(resource_id)
    #         except Exception as e:
    #             failed_list.append(resource_id)
    #             print(f"❌ Failed to save {resource_id}: {e}")

    #     tasks = [
    #         save_single_resource(res, resource_ids[idx])
    #         for idx, res in enumerate(resources)
    #     ]
    #     await asyncio.gather(*tasks)

    #     # ✅ 失敗したリソースの ID を `resource_id_manager` に破棄依頼
    #     # if failed_list:
    #     #    self.resource_id_manager.release_resource_ids(user_id, failed_list)

    #     return {"success": success_list, "failed": failed_list}

    def save_resource(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[ResourceMeta] = None,
        content_file: Optional[BytesIO] = None,
        content_id: Optional[int] = None,
        thumbnail_file: Optional[BytesIO] = None,
    ) -> Optional[str]:
        """
        Saves a resource by storing its metadata, content, and optional thumbnail.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_type (str): The type of the resource (e.g., 'books', 'documents').
            resource_id (str): A unique identifier for the resource.
            metadata (Optional[dict]): Structured metadata for the resource.
            content_file (Optional[BytesIO]): The content file as a BytesIO object.
            content_id (Optional[int]): The ID of the content.
            thumbnail_file (Optional[BytesIO]): Optional thumbnail image.

        Returns:
            Optional[str]: The directory path where the resource was saved, or `None` if saving failed.

        Process:
            1. Ensure the resource directory exists.
            2. Save metadata, content, and optional thumbnails using parallel threads.
            3. Validate storage success and handle errors gracefully.
        """
        # Ensure resource directory exists
        resource_dir = self._get_resource_dir(user_id, resource_type, resource_id)
        os.makedirs(resource_dir, exist_ok=True)

        try:

            def _save_content(content_data: bytes, content_path: str):
                """Saves the content file."""
                with open(content_path, "wb") as f:
                    f.write(content_data)

            def _save_metadata(metadata: ResourceMeta, metadata_path: str):
                """Saves metadata as a JSON file."""
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=4)
                self._update_user_metadata(user_id, resource_type)

            with ThreadPoolExecutor(max_workers=4) as executor:
                # Save content if provided
                if content_file and content_id is not None:
                    content_data = content_file.getvalue()
                    content_path = self._get_content_path(
                        user_id, resource_type, resource_id, content_id
                    )
                    future_content = executor.submit(
                        _save_content, content_data, content_path
                    )

                # Save metadata if provided
                if metadata:
                    metadata_path = self._get_metadata_path(
                        user_id, resource_type, resource_id
                    )
                    future_metadata = executor.submit(
                        _save_metadata, metadata, metadata_path
                    )

                # Process thumbnails if provided
                if thumbnail_file:
                    (
                        original_thumbnail_path,
                        small_thumbnail_path,
                        medium_thumbnail_path,
                        large_thumbnail_path,
                    ) = self._get_thumbnail_path(user_id, resource_type, resource_id)

                    thumbnail_futures = {
                        "original": executor.submit(
                            image_processor.convert_image,
                            thumbnail_file,
                            original_thumbnail_path,
                            "WEBP",
                            quality=100,
                        )
                    }

                    # Generate resized thumbnails separately
                    thumbnail_futures.update(
                        {
                            "small": executor.submit(
                                image_processor.convert_image,
                                BytesIO(thumbnail_file.getvalue()),
                                small_thumbnail_path,
                                "WEBP",
                                width=100,
                                height=100,
                                quality=85,
                            ),
                            "medium": executor.submit(
                                image_processor.convert_image,
                                BytesIO(thumbnail_file.getvalue()),
                                medium_thumbnail_path,
                                "WEBP",
                                width=200,
                                height=200,
                                quality=85,
                            ),
                            "large": executor.submit(
                                image_processor.convert_image,
                                BytesIO(thumbnail_file.getvalue()),
                                large_thumbnail_path,
                                "WEBP",
                                width=300,
                                height=300,
                                quality=85,
                            ),
                        }
                    )

                # Validate metadata saving
                if metadata:
                    try:
                        future_metadata.result()
                    except Exception as e:
                        logging.error(f"Metadata save failed: {e}")
                        return None

                # Validate content saving
                if content_file:
                    try:
                        future_content.result()
                    except Exception as e:
                        logging.error(f"Content save failed: {e}")

                # Validate thumbnails saving
                if thumbnail_file:
                    for size, future in thumbnail_futures.items():
                        try:
                            future.result()
                        except Exception as e:
                            logging.error(
                                f"Thumbnail generation failed for {size}: {e}"
                            )

        except Exception as e:
            raise RuntimeError(f"Failed to save resource {resource_id}: {str(e)}")

        return resource_dir

    def save_resource_meta(
        self, user_id: str, resource_type: str, resource_id: str, metadata: ResourceMeta
    ) -> Optional[str]:
        """
        Saves resource metadata using the primary `save_resource` method.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_type (str): The type of the resource (e.g., 'books', 'documents').
            resource_id (str): The unique identifier for the resource.
            metadata (dict): Metadata information to be saved.

        Returns:
            Optional[str]: The directory path where the metadata was saved, or `None` if saving failed.

        Process:
            1. Calls `save_resource()` with metadata to store it appropriately.
            2. Returns the directory path of the saved resource metadata.
        """
        return self.save_resource(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )

    def save_thumbnail(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        thumbnail: bytes,
        thumbnail_size: str,
    ):
        logging.info("save_thumbnail")
        (
            original_thumbnail_path,
            small_thumbnail_path,
            medium_thumbnail_path,
            large_thumbnail_path,
        ) = self._get_thumbnail_path(user_id, resource_type, resource_id)
        # Determine the correct file path
        thumbnail_path_map = {
            "original": original_thumbnail_path,
            "small": small_thumbnail_path,
            "medium": medium_thumbnail_path,
            "large": large_thumbnail_path,
        }
        thumbnail_path = thumbnail_path_map.get(thumbnail_size)
        if thumbnail_path:
            try:
                with open(thumbnail_path, "wb") as f:
                    f.write(thumbnail)
            except Exception as e:
                logging.error(f"Error: Failed to save thumbnail.")

    def delete_resource(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> bool:
        """
        Deletes the specified resource and its associated directory.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_type (str): The type of the resource (e.g., 'books', 'documents').
            resource_id (str): The unique identifier for the resource.

        Returns:
            bool: `True` if the resource was successfully deleted, `False` otherwise.

        Process:
            1. Determine the resource directory path.
            2. Verify if the directory exists. If not, log a warning and return `False`.
            3. Attempt to delete the directory and its contents.
            4. Log success if deletion is successful, otherwise log the exception.
        """
        # Determine the resource directory path
        resource_dir = self._get_resource_dir(user_id, resource_type, resource_id)

        # Verify directory existence
        if not os.path.isdir(resource_dir):
            logging.warning(f"Resource directory not found: {resource_dir}")
            return False

        try:
            # Delete the entire directory and its contents
            shutil.rmtree(resource_dir, ignore_errors=True)
            self._update_user_metadata(user_id, resource_type)
            logging.info(f"Resource deleted: {resource_dir}")

            return True
        except Exception as e:
            logging.exception(f"Failed to delete resource {resource_dir}: {e}")
            return False

    def delete_resource_content(
        self, user_id: str, resource_type: str, resource_id: str, content_id: int
    ) -> bool:
        """
        Deletes the specified content from the given resource.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_type (str): The type of the resource (e.g., 'books', 'documents').
            resource_id (str): The unique identifier for the resource.
            content_id (int): The unique identifier for the content to be deleted.

        Returns:
            bool: `True` if the content was successfully deleted, `False` otherwise.

        Process:
            1. Determine the resource directory path.
            2. Verify if the directory exists. If not, log a warning and return `False`.
            3. Identify matching content files using wildcard search.
            4. If no matching files are found, log a warning and return `False`.
            5. Delete each matching file and log the deletion status.
            6. Return `True` upon successful deletion.
        """
        # Determine the resource directory path
        resource_dir = self._get_resource_dir(user_id, resource_type, resource_id)

        # Check if the directory exists; if not, log a warning and return `False`
        if not os.path.isdir(resource_dir):
            logging.warning(f"Resource directory not found: {resource_dir}")
            return False

        try:
            # Identify all matching content files
            content_paths = glob.glob(
                self._get_content_path(user_id, resource_type, resource_id, content_id)
            )

            if not content_paths:
                logging.warning(f"No matching content found for ID {content_id}")
                return False

            # Delete each matching file
            for path in content_paths:
                os.remove(path)
                logging.info(f"Deleted content: {path}")

            return True
        except Exception as e:
            logging.error(
                f"Failed to delete content {content_id} in {resource_dir}: {e}"
            )
            return False

    def exist_thumbnail(
        self, user_id: str, resource_type: str, resource_id: str, size: str
    ) -> bool:
        paths = dict(
            zip(
                ["original", "small", "medium", "large"],
                self._get_thumbnail_path(user_id, resource_type, resource_id),
            )
        )
        return os.path.exists(paths.get(size, ""))

    # def get_load_resource(self, user_id: str, resource_type: str, resource_id: str):
    #     """
    #     Loads the metadata, content, and thumbnail for a given resource ID.
    #     Returns None if the resource does not exist.
    #     """
    #     metadata = self.load_resource_meta(user_id, resource_type, resource_id)

    #     if metadata is None:
    #         return None  # リソースが存在しない場合

    #     resource_dir = self._get_resource_dir(user_id, resource_type, resource_id)

    #     # コンテンツの拡張子を取得
    #     available_formats = metadata.get("available_formats", set())
    #     content_path = None
    #     for extension in available_formats:
    #         potential_path = os.path.join(resource_dir, f"content.{extension}")
    #         if os.path.exists(potential_path):
    #             content_path = potential_path
    #             break

    #     if content_path is None:
    #         return None  # コンテンツが見つからない場合

    #     thumbnail_path = self._get_thumbnail_path(user_id, resource_type, resource_id)

    #     try:
    #         # コンテンツの読み込み
    #         with open(content_path, "rb") as f:
    #             content = f.read()

    #         # サムネイルの読み込み
    #         thumbnail = None
    #         if os.path.exists(thumbnail_path):
    #             with open(thumbnail_path, "rb") as f:
    #                 thumbnail = f.read()

    #         return {
    #             "metadata": metadata,
    #             "content": content,
    #             "thumbnail": thumbnail,
    #             "extension": os.path.splitext(content_path)[1][1:],  # ファイル拡張子
    #         }

    #     except Exception as e:
    #         raise RuntimeError(f"Failed to load resource {resource_id}: {str(e)}")

    # def load_resource(
    #     self, user_id: str, resource_type: str, resource_id: str
    # ) -> dict | None:
    #     """
    #     Loads the metadata, content, and thumbnail for a given resource ID.
    #     Returns None if the resource does not exist.
    #     """
    #     metadata = self.load_resource_meta(user_id, resource_type, resource_id)

    #     if metadata is None:
    #         return None  # リソースが存在しない場合

    #     resource_dir = self._get_resource_dir(user_id, resource_type, resource_id)

    #     # コンテンツの拡張子を取得
    #     available_formats = metadata.get("available_formats", set())
    #     content_path = None
    #     for extension in available_formats:
    #         potential_path = os.path.join(resource_dir, f"content.{extension}")
    #         if os.path.exists(potential_path):
    #             content_path = potential_path
    #             break

    #     if content_path is None:
    #         return None  # コンテンツが見つからない場合

    #     thumbnail_path = self._get_thumbnail_path(user_id, resource_type, resource_id)

    #     try:
    #         # コンテンツの読み込み
    #         with open(content_path, "rb") as f:
    #             content = f.read()

    #         # サムネイルの読み込み
    #         thumbnail = None
    #         if os.path.exists(thumbnail_path):
    #             with open(thumbnail_path, "rb") as f:
    #                 thumbnail = f.read()

    #         return {
    #             "metadata": metadata,
    #             "content": content,
    #             "thumbnail": thumbnail,
    #             "extension": os.path.splitext(content_path)[1][1:],  # ファイル拡張子
    #         }

    #     except Exception as e:
    #         raise RuntimeError(f"Failed to load resource {resource_id}: {str(e)}")

    # def count_resources(self, user_id: str, resource_type: str) -> int:
    #     """Counts the number of resources for a given user and type."""
    #     resource_type_dir = self._get_resource_type_dir(user_id, resource_type)

    #     if not os.path.exists(resource_type_dir):
    #         return 0

    #     # `resource.json` の数をカウント
    #     return sum(
    #         1
    #         for root, _, files in os.walk(resource_type_dir)
    #         if "metadata.json" in files
    #     )
