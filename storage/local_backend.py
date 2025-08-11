# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import json
import os

from storage.abstract_backend import AbstractStorageBackend


class LocalStorageBackend(AbstractStorageBackend):
    """Handles resource storage using local file system."""

    def __init__(self, base_dir="resources"):
        """Initializes the storage backend with a base directory."""
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)  # ルートディレクトリを作成

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

    def _get_resource_path(self, user_id: str, resource_id: str, file_type: str) -> str:
        """Returns the file path for a given resource."""
        return os.path.join(self.base_dir, user_id, resource_id, f"{file_type}.json")

    def save(self, user_id: str, resource_id: str, file_type: str, data: dict) -> str:
        """Saves JSON resource data to local storage."""
        file_path = self._get_resource_path(user_id, resource_id, file_type)
        os.makedirs(
            os.path.dirname(file_path), exist_ok=True
        )  # 必要なディレクトリを作成

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            raise RuntimeError(f"Failed to save resource {resource_id}: {str(e)}")

        return file_path

    def load(self, user_id: str, resource_id: str, file_type: str) -> dict | None:
        """Loads JSON resource data from local storage."""
        file_path = self._get_resource_path(user_id, resource_id, file_type)

        if not os.path.exists(file_path):
            return None  # ファイルが存在しない場合は `None` を返す

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load resource {resource_id}: {str(e)}")

    def delete(self, user_id: str, resource_id: str, file_type: str) -> bool:
        """Deletes a resource file from local storage."""
        file_path = self._get_resource_path(user_id, resource_id, file_type)

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        except Exception as e:
            raise RuntimeError(f"Failed to delete resource {resource_id}: {str(e)}")

        return False

    def load_resource_meta(
        self, user_id: str, resource_type: str, resource_id: str
    ) -> dict | None:
        """
        Loads metadata for a given resource ID.
        Returns None if the resource does not exist.
        """
        json_path = self.__get_json_path(user_id, resource_type, resource_id)

        if not os.path.exists(json_path):
            return None

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                resource_data = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load metadata for {resource_id}: {str(e)}")

        return resource_data.get("metadata", None)  # メタデータのみを抽出
