# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging

from google.auth.transport import requests
from google.oauth2 import id_token

from config.settings import GOOGLE_CLIENT_ID

from .base import OAuthProvider


class GoogleOAuth(OAuthProvider):
    def verify_token(self, token: str) -> dict | None:
        try:
            idinfo = id_token.verify_oauth2_token(
                token, requests.Request(), GOOGLE_CLIENT_ID
            )
            return {"id": idinfo["sub"], "email": idinfo["email"], "provider": "google"}
        except Exception as e:
            logging.error(f"[GoogleOAuth] Verification failed: {e}")
            return None
