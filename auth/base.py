# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

from abc import ABC, abstractmethod


class OAuthProvider(ABC):
    @abstractmethod
    def verify_token(self, token: str) -> dict | None:
        pass
