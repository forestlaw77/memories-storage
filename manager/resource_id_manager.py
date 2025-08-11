# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed under the MIT License for non-commercial use.

import threading
from typing import Dict, List, Set

import ulid

from storage.abstract_backend import AbstractStorageBackend


class ResourceIdManager:
    """
    Manages `resource_id` assignments for a given resource type.
    - Stores `resource_id` as a set for optimal lookups and modifications.
    - Provides a thread-safe structure using `threading.Lock`.
    """

    def __init__(self, resource_name: str, storage_backend: AbstractStorageBackend):
        """
        Initializes the resource ID manager.

        Args:
            resource_name (str): The type of the resource (e.g., 'books', 'documents').
            storage_backend (AbstractStorageBackend): The backend used for storage operations.
        """
        self.ids: Dict[str, Set[str]] = {}
        self.lock: threading.Lock = threading.Lock()
        self.storage_backend: AbstractStorageBackend = storage_backend
        self.resource_name: str = resource_name

    def _ensure_user_ids_loaded(self, user_id: str) -> None:
        """
        Ensures that the user's resource IDs are loaded into memory.

        Args:
            user_id (str): The ID of the user whose resources should be loaded.

        Process:
            1. Check if the user ID is already initialized.
            2. If not, load resource IDs from storage and store them as a set.
        """
        if user_id not in self.ids:
            self.ids[user_id] = set(
                self.storage_backend.get_resource_list(user_id, self.resource_name)
            )

    def generate_resource_id(self, user_id: str) -> str:
        """
        Generates a unique resource ID using UUID.

        Args:
            user_id (str): The ID of the user who owns the resource.

        Returns:
            str: A newly generated unique resource ID.

        Process:
            1. Acquire thread lock for safe concurrent modifications.
            2. Generate a new UUID-based resource ID.
            3. Store the new resource ID in the set.
            4. Return the newly created resource ID.
        """
        with self.lock:
            self._ensure_user_ids_loaded(user_id)
            # resource_id = str(uuid.uuid4())
            resource_id = self._create_ulid()
            self.ids[user_id].add(resource_id)
        return resource_id

    def _create_ulid(self) -> str:
        """Generates a ULID as a unique resource identifier."""
        return str(ulid.new())

    def release_resource_id(self, user_id: str, resource_id: str) -> None:
        """
        Deletes a resource ID for a user.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The unique identifier for the resource.

        Process:
            1. Acquire thread lock for safe concurrent access.
            2. Remove the specified `resource_id` from the set.
        """
        with self.lock:
            self._ensure_user_ids_loaded(user_id)
            self.ids.get(user_id, set()).discard(resource_id)

    def get_resource_list(self, user_id: str) -> List[str]:
        """
        Retrieves a list of resource IDs for a user.

        Args:
            user_id (str): The ID of the user who owns the resources.

        Returns:
            List[str]: A list of resource IDs.

        Process:
            1. Acquire thread lock for safe concurrent access.
            2. Convert the stored set to a list before returning.
        """
        with self.lock:
            self._ensure_user_ids_loaded(user_id)
            return list(self.ids.get(user_id, set()))

    def count_resources(self, user_id: str) -> int:
        """
        Returns the number of resources associated with a user.

        Args:
            user_id (str): The ID of the user whose resources should be counted.

        Returns:
            int: The number of resources available for the user.

        Process:
            1. Acquire thread lock for safe concurrent access.
            2. Return the length of the stored set.
        """
        with self.lock:
            self._ensure_user_ids_loaded(user_id)
            return len(self.ids.get(user_id, set()))

    def exist_resource(self, user_id: str, resource_id: str) -> bool:
        """
        Checks if a resource ID exists for a user.

        Args:
            user_id (str): The ID of the user who owns the resource.
            resource_id (str): The unique identifier for the resource.

        Returns:
            bool: `True` if the resource exists, `False` otherwise.

        Process:
            1. Acquire thread lock for safe concurrent access.
            2. Verify presence of the `resource_id` in the stored set.
        """
        with self.lock:
            self._ensure_user_ids_loaded(user_id)
            return resource_id in self.ids.get(user_id, set())
