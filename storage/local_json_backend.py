# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import json
import os
import threading

from storage.abstract_backend import AbstractStorageBackend


class LocalStorageJsonBackend(AbstractStorageBackend):
    """Handles resource storage using local JSON file system."""

    def __init__(self, base_dir="resources"):
        """Initializes the storage backend with a base directory."""
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def __get_json_path(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> str:
        """Returns the JSON file path for a given resource, including resource type."""
        return os.path.join(
            self.base_dir,
            "json",
            user_id,
            resource_type,
            resource_id[:2],
            resource_id,
            "resource.json",
        )

    def count_resources(self, user_id: str, resource_type: str) -> int:
        """Counts the number of resources for a given user and type."""
        resource_dir = os.path.join(self.base_dir, "json", user_id, resource_type)

        if not os.path.exists(resource_dir):
            return 0

        # `resource.json` の数をカウント
        return sum(
            1 for root, _, files in os.walk(resource_dir) if "resource.json" in files
        )

    def save_resource(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        metadata: dict,
        content: bytes = b"",
        thumbnail: bytes = b"",
    ) -> str:
        """Saves a resource in a thread-safe JSON structure."""
        json_path = self.__get_json_path(user_id, resource_type, resource_id)
        os.makedirs(os.path.dirname(json_path), exist_ok=True)

        resource_data = {
            "resource_id": resource_id,
            "metadata": metadata,
            "content": content.decode("utf-8"),
            "thumbnail": thumbnail.decode("utf-8"),
        }

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(resource_data, f, indent=4)
        except Exception as e:
            raise RuntimeError(f"Failed to save JSON resource {resource_id}: {str(e)}")

        return json_path

    def load_resource(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> dict | None:
        """Loads a resource in a thread-safe manner."""
        json_path = self.__get_json_path(user_id, resource_type, resource_id)

        if not os.path.exists(json_path):
            return None

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load JSON resource {resource_id}: {str(e)}")

    def delete_resource(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> bool:
        """Deletes a resource in a thread-safe manner."""
        json_path = self.__get_json_path(user_id, resource_type, resource_id)

        try:
            if os.path.exists(json_path):
                os.remove(json_path)
                return True
        except Exception as e:
            raise RuntimeError(
                f"Failed to delete JSON resource {resource_id}: {str(e)}"
            )

        return False

    def load_resource_meta(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> dict | None:
        """
        Loads metadata for a given resource from JSON storage.
        Returns None if the resource does not exist.
        """
        resource_key = f"{user_id}:{resource_type}:{resource_id}"

        if resource_key not in self.json_storage:
            return None

        return self.json_storage[resource_key].get(
            "metadata", None
        )  # メタデータのみ取得

    def load_resource_content():
        pass

    def load_resource_thumbnail():
        pass

    def get_resource_list(self, user_id: str, resource_type: str) -> list:
        pass
