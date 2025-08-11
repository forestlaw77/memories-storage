# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

from http import HTTPStatus

from flask import Blueprint, jsonify, make_response
from flask_cors import cross_origin

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint.

    Returns:
        Response: JSON response indicating the service is healthy.
    """
    return make_response(jsonify({"status": "healthy"}), HTTPStatus.OK)


@health_bp.route("/health", methods=["OPTIONS"])
@cross_origin()
def health_options():
    """Handles CORS preflight request.

    Returns:
        Response: Empty JSON response with status code 204.
    """
    return make_response(jsonify({}), HTTPStatus.NO_CONTENT)
