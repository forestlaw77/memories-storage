# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging
from functools import wraps
from http import HTTPStatus

from flask import Blueprint, g, jsonify, make_response, request
from flask_cors import cross_origin

from auth.verify_auth_token import get_user_id, verify_oauth_token
from auth.verify_auth_token_auto import verify_oauth_token_auto
from services.init import storage_backend

users_bp = Blueprint("users", __name__)


def log_api_call(f):
    """Decorator to log API calls.
    This decorator logs the HTTP method and path of the API call.
    Args:
        f (function): The function to be decorated.
    Returns:
        function: The wrapped function with logging functionality.
    """

    # import logging
    @wraps(f)  # Preserve the original function's metadata
    def wrapper(*args, **kwargs):
        # logging.info(f"[{request.method}] API Call: {request.path}")
        return f(*args, **kwargs)

    return wrapper


@users_bp.route("/settings", methods=["POST"])
@log_api_call
@verify_oauth_token
def post_user_settings():
    return make_response(jsonify({"status": "success"}), HTTPStatus.OK)


@users_bp.route("/settings", methods=["GET"])
@log_api_call
@verify_oauth_token
def get_user_settings():
    return make_response(jsonify({"status": "success"}), HTTPStatus.OK)


@users_bp.route("/meta", methods=["GET"])
@log_api_call
@verify_oauth_token
def get_user_metadata():
    user_id: str = get_user_id(g.user_info, g.auth_provider)
    logging.info(f"user_id:{user_id}")
    user_meta = storage_backend.load_user_metadata(user_id)
    response = {"status": "success", "message": "success", "response_data": user_meta}
    return make_response(response, HTTPStatus.OK)


@users_bp.route("/check", methods=["OPTIONS"])
@log_api_call
@cross_origin()
def options_resource():
    """Handles CORS preflight request.

    Returns:
        Response: Empty JSON response with status code 204.
    """
    return make_response(jsonify({}), HTTPStatus.NO_CONTENT)


@users_bp.route("/check", methods=["POST"])
@log_api_call
@verify_oauth_token
def check_user():
    """ユーザーが登録済みか確認"""
    user_id: str = get_user_id(g.user_info, g.auth_provider)
    user_meta = storage_backend.load_user_metadata(user_id)

    if not user_meta:
        return make_response(
            {"exists": False, "message": "User not registered"}, HTTPStatus.NOT_FOUND
        )

    return make_response({"exists": True, "user": user_meta}, HTTPStatus.OK)


@users_bp.route("/register", methods=["POST"])
@log_api_call
@verify_oauth_token  # ✅ OAuth 認証を適用
def register_user():
    """OAuth 認証済みのユーザーを登録し、user_meta を保存"""
    user_id: str = get_user_id(g.user_info, g.auth_provider)
    email = g.user_info.get("email")
    name = g.user_info.get("name")

    if not email or not user_id:
        return make_response({"error": "Invalid token"}, HTTPStatus.UNAUTHORIZED)

    # すでに登録されているかチェック
    existing_meta = storage_backend.load_user_metadata(user_id)
    if existing_meta:
        return make_response(
            {"message": "User already exists", "user": existing_meta}, HTTPStatus.OK
        )

    # ✅ `user_meta` を作成
    user_meta = {
        "id": user_id,
        "name": name,
        "email": email,
        "role": "user",
        "resources": {},
    }

    # ✅ `storage_backend` に保存
    storage_backend.save_user_metadata(user_id, user_meta)

    return make_response(
        {"message": "User registered successfully", "user": user_meta},
        HTTPStatus.CREATED,
    )


# # 仮のユーザーDB
# users_db = {}


# @users_bp.route("/register", methods=["POST"])
# @verify_oauth_token  # ✅ デコレーターを適用
# def register_user():
#     """OAuth 認証済みのユーザーを登録"""
#     email = g.user_info.get("email")
#     if not email:
#         return jsonify({"error": "Invalid token"}), 401

#     if email in users_db:
#         return jsonify({"message": "User already exists", "user": users_db[email]}), 200

#     users_db[email] = {"name": g.user_info.get("name"), "email": email}
#     return (
#         jsonify({"message": "User registered successfully", "user": users_db[email]}),
#         201,
#     )
