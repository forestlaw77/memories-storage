# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import base64
import json


def decode_jwt_without_verify(token: str):
    try:
        header, payload, signature = token.split(".")
        payload_bytes = base64.urlsafe_b64decode(payload + "==")
        return json.loads(payload_bytes)
    except Exception:
        return {}


def detect_provider(token: str) -> str | None:
    if token.count(".") == 2:
        payload = decode_jwt_without_verify(token)
        iss = payload.get("iss", "")
        aud = payload.get("aud", "")

        if "accounts.google.com" in iss or "googleusercontent.com" in aud:
            return "google"
        if "sts.windows.net" in iss or "microsoft" in aud:
            return "microsoft"
        # 他の JWT ベースプロバイダーがあればここに条件追加

    # JWT でない場合は GitHub の可能性大
    return "github"
