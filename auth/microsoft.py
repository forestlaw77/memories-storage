# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging

import requests

# MICROSOFT_USERINFO_URL = "https://graph.microsoft.com/oidc/userinfo"
from config.settings import MICROSOFT_OAUTH_USERINFO_URL

from .base import OAuthProvider


class MicrosoftOAuth(OAuthProvider):
    def verify_token(self, token: str) -> dict | None:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(MICROSOFT_OAUTH_USERINFO_URL, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "id": data.get("sub"),
                    "email": data.get("email") or data.get("preferred_username"),
                    "provider": "microsoft",
                }
        except Exception as e:
            logging.error(f"[MicrosoftOAuth] Verification error: {e}")
        return None
