#!/usr/bin/env python3
import sys

sys.path.append("../")
import subprocess
import argparse
from storage.local_bare_backend import LocalStorageBareBackend

paser = argparse.ArgumentParser(description="")


class ResourceManager:
    def __init__(self, storage_api_url: str):
        self.storage_api_url = storage_api_url
        self.local_backend = LocalStorageBareBackend("/src/local_storage")

    def is_server_running(self) -> bool:
        try:
            response = subprocess.run(
                ["curl", "-s", f"{self.storage_api_url}/health"],
                capture_output=True,
                text=True,
            )
            return response.returncode == 0
        except Exception:
            return False

    def get_resource_list(self):
        if self.is_server_running():
            response = subprocess.run(
                ["curl", "-s", f"{self.storage_api_url}/music/"],
                capture_output=True,
                text=True,
            )
            return response.stdout  # ✅ API からリソース取得
        else:
            return self.local_backend.get_resource_list(
                USRID, "music"
            )  # ✅ ローカルからリソース取得


rm = ResourceManager("http://localhost:4001/v1")

print(rm.get_resource_list())
