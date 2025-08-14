# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging
import os
import uuid
from functools import wraps

import requests
from flask import g, jsonify, request

from config.settings import (
    GITHUB_OAUTH_USERINFO_URL,
    GOOGLE_OAUTH_USERINFO_URL,
    MICROSOFT_OAUTH_USERINFO_URL,
)

TEST_MODE = False

SKIP_AUTH = os.getenv("SKIP_AUTH", "false").lower() == "true"


def verify_oauth_token(f):
    """OAuth トークンを検証し、ユーザー情報をリクエスト全体で保持"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "OPTIONS":
            logging.debug(
                f"--- DEBUG: Detected OPTIONS method. Skipping token verification for path: {request.path}"
            )
            return f(*args, **kwargs)

        if SKIP_AUTH:
            logging.debug(
                "[verify_oauth_token] SKIP_AUTH is enabled. Injecting local-user."
            )
            g.user_info = {
                "email": "local@example.com",
                "sub": "local-user",
                "provider": "local",
            }
            g.auth_provider = "local"
            return f(*args, **kwargs)

        if TEST_MODE:
            g.user_info = {"id": "forestlaw", "email": "test@example.com"}
            g.auth_provider = "test"
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization")
        logging.info(
            f"[verify_oauth_token] Received Authorization Header: {auth_header}"
        )

        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401

        token = auth_header.split(" ")[1]
        logging.info(f"[verify_oauth_token]token:{token}")
        user_info = authenticate_oauth_token(token)

        if not user_info:
            return jsonify({"error": "Invalid token"}), 401

        g.user_info = user_info
        g.auth_provider = user_info["provider"]
        return f(*args, **kwargs)

    return decorated_function


def authenticate_oauth_token(token: str):
    """Google, Microsoft, GitHub の OAuth トークンを検証"""
    oauth_providers = {
        "google": GOOGLE_OAUTH_USERINFO_URL,
        "microsoft": MICROSOFT_OAUTH_USERINFO_URL,
        "github": GITHUB_OAUTH_USERINFO_URL,
    }

    for provider, url in oauth_providers.items():
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            user_info = response.json()
            user_info["provider"] = provider

            # GitHub はデフォルトで email を返さないため、追加リクエストを実施
            if provider == "github":
                email_response = requests.get(
                    "https://api.github.com/user/emails", headers=headers
                )
                if email_response.status_code == 200:
                    emails = email_response.json()
                    primary_email = next(
                        (email["email"] for email in emails if email["primary"]), None
                    )
                    user_info["email"] = primary_email

            return user_info
    logging.error("Error")
    return None


# 固定の名前空間（アプリ全体で統一するため）
NAMESPACE_OAUTH = uuid.UUID("12345678-1234-5678-1234-567812345678")


def get_user_id(user_info: dict, provider: str) -> str:
    """OAuth プロバイダーに関係なく統一された 36 桁の user_id を生成"""
    provider_map = {
        "test": user_info.get("id", ""),
        "local": user_info.get("sub", "") or user_info.get("id", ""),
        "google": user_info.get("sub", "") or user_info.get("id", ""),
        "microsoft": user_info.get("oid", "") or user_info.get("sub", ""),
        "github": str(user_info.get("id", "")),
    }

    raw_user_id = provider_map.get(provider)
    if not raw_user_id:
        logging.error(
            f"[get_user_id] Missing raw user id for provider: {provider}, user_info: {user_info}"
        )
        raise ValueError(f"Invalid provider or missing user_id: {provider}")

    user_id = str(uuid.uuid5(NAMESPACE_OAUTH, raw_user_id))
    return user_id
