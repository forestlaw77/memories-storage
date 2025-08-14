# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging
import os
from functools import wraps

from flask import g, jsonify, request

from auth.factory import get_oauth_provider
from auth.utils import detect_provider
from config.settings import SKIP_AUTH


def verify_oauth_token_auto(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if SKIP_AUTH:
            logging.debug("--- DEBUG: SKIP_AUTH is enabled. Injecting mock user.")
            g.user_info = {
                "email": "local@example.com",
                "name": "Local User",
                "provider": "local",
                "sub": "local-user-id",
            }
            g.auth_provider = "local"
            return f(*args, **kwargs)

        if request.method == "OPTIONS":
            logging.debug(
                f"--- DEBUG: Detected OPTIONS method. Skipping token verification for path: {request.path}"
            )
            return f(*args, **kwargs)

        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return jsonify({"error": "Missing Bearer token"}), 401

        token = auth.split(" ")[1]
        provider_name = detect_provider(token)
        if not provider_name:
            return jsonify({"error": "Unable to detect provider"}), 400

        provider = get_oauth_provider(provider_name)
        if not provider:
            return jsonify({"error": f"Unsupported provider: {provider_name}"}), 400

        user_info = provider.verify_token(token)
        if not user_info:
            return jsonify({"error": "Invalid token"}), 401

        g.user_info = user_info
        g.auth_provider = user_info["provider"]
        return f(*args, **kwargs)

    return decorated_function
