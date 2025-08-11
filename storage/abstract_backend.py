# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

from abc import ABC, abstractmethod
from io import BytesIO
from typing import List, Optional

from werkzeug.datastructures import FileStorage

from models.types import ResourceMeta


class AbstractStorageBackend(ABC):
    @abstractmethod
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
        pass

    @abstractmethod
    def load_resource_meta(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> Optional[ResourceMeta]:
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def save_resource_meta(
        self, user_id: str, resource_type: str, resource_id: str, metadata: ResourceMeta
    ) -> str:
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
        pass

    @abstractmethod
    def save_thumbnail(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        thumbnail: bytes,
        thumbnail_size: str,
    ):
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def exist_thumbnail(
        self, user_id: str, resource_type: str, resource_id: str, size: str
    ) -> bool:
        pass

    @abstractmethod
    def load_user_metadata(self, user_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    def save_user_metadata(self, user_id: str, metadata: dict) -> bool:
        pass
