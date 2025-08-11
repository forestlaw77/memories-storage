# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed under the MIT License for non-commercial use.

import threading

from storage.abstract_backend import AbstractStorageBackend


class ContentIdManager:
    """
    Manages `content_id` assignments for a given resource type.
    - Maintains a persistent set of content IDs per user and resource.
    - Ensures thread-safe operations using `threading.Lock`.
    """

    def __init__(self, resource_name: str, storage_backend: AbstractStorageBackend):
        """
        Initializes the content ID manager.

        Args:
            resource_name (str): The type of the resource (e.g., 'books', 'documents').
            storage_backend (AbstractStorageBackend): The backend used for storage operations.
        """
        self.resource_name = resource_name
        self.storage_backend = storage_backend
        self.content_id_manager = {}
        self.lock: threading.Lock = threading.Lock()

    def __initialize_content_id(self, user_id: str, resource_id: str):
        """
        Loads existing content IDs from the metadata file if available.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The unique identifier for the resource.

        Process:
            1. Ensure a content ID set exists for the given `user_id` and `resource_id`.
            2. Load metadata from storage backend if available.
            3. Extract `content_ids` into a set or initialize an empty set.
        """
        if user_id not in self.content_id_manager:
            self.content_id_manager[user_id] = {}

        if resource_id not in self.content_id_manager[user_id]:
            # Retrieve metadata and initialize content ID set
            resource_meta = self.storage_backend.load_resource_meta(
                user_id, self.resource_name, resource_id
            )
            if not resource_meta:
                self.content_id_manager[user_id][resource_id] = set()
                return
            basic_meta = resource_meta.get("basic_meta", {})
            if not basic_meta:
                self.content_id_manager[user_id][resource_id] = set()
                return
            content_ids = basic_meta.get("content_ids", [])
            if not content_ids:
                self.content_id_manager[user_id][resource_id] = set()
                return
            self.content_id_manager[user_id][resource_id] = set(content_ids)

    def generate_content_id(self, user_id: str, resource_id: str) -> int:
        """
        Generates the next available `content_id` within a resource.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The unique identifier for the resource.

        Returns:
            int: The next available `content_id`.

        Process:
            1. Acquire thread lock for safe concurrent access.
            2. Load existing IDs and determine the next available ID.
            3. Prioritize IDs from `1` to `9`, then find the lowest unused integer.
            4. Add the assigned `content_id` to the set and return it.
        """
        with self.lock:
            self.__initialize_content_id(user_id, resource_id)

            existing_ids = self.content_id_manager[user_id][resource_id]

            # Prioritize IDs in range 1-9
            for content_id in range(1, 10):
                if content_id not in existing_ids:
                    existing_ids.add(content_id)
                    return content_id

            # Find the lowest available integer beyond 9
            new_id = min(set(range(1, 100)) - existing_ids)
            existing_ids.add(new_id)
            return new_id

    def release_content_id(self, user_id: str, resource_id: str, content_id: int):
        """
        Releases a `content_id` when content is deleted.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The unique identifier for the resource.
            content_id (int): The content ID to be released.

        Process:
            1. Acquire thread lock for safe concurrent modifications.
            2. Remove the specified `content_id` from the active set.
        """
        with self.lock:
            self.__initialize_content_id(user_id, resource_id)
            if (
                user_id in self.content_id_manager
                and resource_id in self.content_id_manager[user_id]
            ):
                self.content_id_manager[user_id][resource_id].discard(content_id)

    def exist_content(self, user_id: str, resource_id: str, content_id: int) -> bool:
        """
        Checks if a `content_id` exists for a given resource.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The unique identifier for the resource.
            content_id (int): The content ID to check.

        Returns:
            bool: `True` if the content exists, `False` otherwise.

        Process:
            1. Acquire thread lock for safe concurrent access.
            2. Verify if the `content_id` is present in the active set.
        """
        with self.lock:
            self.__initialize_content_id(user_id, resource_id)
            return content_id in self.content_id_manager[user_id].get(
                resource_id, set()
            )

    def get_content_list(self, user_id: str, resource_id: str) -> list:
        """
        Retrieves all `content_ids` for a specified resource.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The unique identifier for the resource.

        Returns:
            list: A list of all `content_ids` associated with the resource.

        Process:
            1. Acquire thread lock to ensure thread-safe access.
            2. Initialize the content ID set if not already loaded.
            3. Retrieve and return the list of `content_ids`.
        """
        with self.lock:
            self.__initialize_content_id(user_id, resource_id)
            return list(self.content_id_manager[user_id].get(resource_id, set()))
