# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

from .github import GitHubOAuth  # 同様に定義するとして
from .google import GoogleOAuth
from .microsoft import MicrosoftOAuth


def get_oauth_provider(provider: str):
    if provider == "google":
        return GoogleOAuth()
    elif provider == "microsoft":
        return MicrosoftOAuth()
    elif provider == "github":
        return GitHubOAuth()
    return None
