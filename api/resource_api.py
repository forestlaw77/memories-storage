# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

from functools import wraps
from http import HTTPStatus

from flask import Blueprint, jsonify, make_response, request

# from auth.verify_auth_token import verify_oauth_token
from auth.verify_auth_token_auto import verify_oauth_token_auto
from services.init import resource_service_map

# from flask_cors import cross_origin


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


def create_resource_blueprint(resource_name: str):
    """Creates a Flask Blueprint for a given resource.

    Args:
        resource_name (str): The name of the resource.

    Returns:
        Blueprint: The Flask Blueprint object for the specified resource.
    """
    bp = Blueprint(resource_name, __name__)

    @bp.route("/health", methods=["GET"])
    @log_api_call
    def health_check():
        """Health check endpoint.

        Returns:
            Response: JSON response indicating the service is healthy.
        """
        return jsonify({"status": "healthy"}), HTTPStatus.OK

    @bp.route("/summary", methods=["GET"])
    @verify_oauth_token_auto
    @log_api_call
    def get_resource_summary():
        """Retrieves a summary of resources.

        Returns:
            Response: JSON response with the lsummaryt of resources or an error message.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_resource_summary()

    @bp.route("/", methods=["GET"])
    @verify_oauth_token_auto
    @log_api_call
    def get_resource_list():
        """Retrieves a list of resources.

        Returns:
            Response: JSON response with the list of resources or an error message.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_resource_list()

    @bp.route("/", methods=["POST"])
    @verify_oauth_token_auto
    @log_api_call
    def post_resource():
        """Creates a new resource.

        Returns:
            Response: JSON response with the created resource or an error message.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.make_resource()

    # @bp.route("/", methods=["OPTIONS"])
    # @log_api_call
    # @cross_origin()
    # def options_resource():
    #     """Handles CORS preflight request.

    #     Returns:
    #         Response: Empty JSON response with status code 204.
    #     """
    #     return make_response(jsonify({}), HTTPStatus.NO_CONTENT)

    @bp.route("/ids", methods={"GET"})
    @verify_oauth_token_auto
    @log_api_call
    def get_resource_ids():
        """Retrieves resource IDs.

        Returns:
            Response: JSON response with resource IDs or an error message.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_resource_ids()

    @bp.route("/detail", methods=["POST"])
    @verify_oauth_token_auto
    @log_api_call
    def post_resource_meta():
        """Creates metadata for a resource.

        Returns:
            Response: JSON response with the metadata or an error message.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.make_resource("meta")

    @bp.route("/contents", methods=["POST"])
    @verify_oauth_token_auto
    @log_api_call
    def post_resource_content():
        """Creates content for a resource.

        Returns:
            Response: JSON response with the created content or an error message.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.make_resource("content")

    # @bp.route("/<resource_id>/meta", methods=["GET"])
    @bp.route("/<resource_id>", methods=["GET"])
    @verify_oauth_token_auto
    @log_api_call
    def get_resource(resource_id):
        """Retrieves metadata for a specific resource.

        Args:
            resource_id (str): The unique identifier of the resource.

        Returns:
            Response: JSON response with the metadata or an error message.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_resource_meta(resource_id)

    @bp.route("/<resource_id>", methods=["PUT"])
    @verify_oauth_token_auto
    @log_api_call
    def update_resource(resource_id):
        """Updates the details of a specific resource.

        Args:
            resource_id (str): The unique identifier of the resource.

        Returns:
            Response: JSON response with the updated resource details or an error message.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.put_resource_detail(resource_id)

    @bp.route("/<resource_id>", methods=["DELETE"])
    @verify_oauth_token_auto
    @log_api_call
    def delete_resource(resource_id):
        """Deletes a specific resource.

        Args:
            resource_id (str): The unique identifier of the resource to be deleted.

        Returns:
            Response: JSON response indicating success or an error message if the resource is unknown.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.delete_resource(resource_id)

    @bp.route("/<resource_id>/contents", methods=["POST"])
    @verify_oauth_token_auto
    @log_api_call
    def add_resource_content(resource_id: str):
        """Adds content to a specific resource.

        Args:
            resource_id (str): The unique identifier of the resource to which content is added.

        Returns:
            Response: JSON response indicating success or an error message if the resource is unknown.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.post_resource_content_addition(resource_id)

    @bp.route("/<resource_id>/contents", methods=["GET"])
    @verify_oauth_token_auto
    @log_api_call
    def get_resource_contents(resource_id: str):
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_content_list(resource_id)

    @bp.route("/<resource_id>/contents/<content_id>", methods=["GET"])
    @verify_oauth_token_auto
    @log_api_call
    def get_resource_content(resource_id: str, content_id: int):
        """Retrieves the content list associated with a specific resource.

        Args:
            resource_id (str): The unique identifier of the resource.

        Returns:
            Response: JSON response containing the list of contents for the resource,
            or an error message if the resource is unknown.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_resource_content(resource_id, content_id)

    @bp.route("/<resource_id>/contents/<content_id>", methods=["PUT"])
    @verify_oauth_token_auto
    @log_api_call
    def put_resource_content(resource_id: str, content_id: int):
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.put_resource_content(resource_id, content_id)

    @bp.route("/<resource_id>/contents/<content_id>/<filename>", methods=["GET"])
    @verify_oauth_token_auto
    @log_api_call
    def get_resource_content_file(resource_id: str, content_id: int, filename: str):
        """Retrieves a specific content file for a given resource.

        Args:
            resource_id (str): The unique identifier of the resource.
            content_id (int): The identifier of the specific content within the resource.
            filename (str): The name of the file to be retrieved.

        Returns:
            Response: JSON response containing the requested file data or an error message if the resource is unknown.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_resource_content(resource_id, content_id, filename)

    @bp.route("/<resource_id>/thumbnail", methods=["GET"])
    @verify_oauth_token_auto
    @log_api_call
    def get_resource_thumbnail(resource_id: str):
        """Retrieves the thumbnail image for a specific resource.

        Args:
            resource_id (str): The unique identifier of the resource.

        Returns:
            Response: JSON response containing the thumbnail image data or an error message if the resource is unknown.
        """
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_resource_thumbnail(resource_id)

    @bp.route("/<resource_id>/thumbnail", methods=["PUT"])
    @verify_oauth_token_auto
    @log_api_call
    def put_resource_thumbnail(resource_id: str):
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.put_resource_thumbnail(resource_id)

    @bp.route("/<resource_id>/thumbnail", methods=["PATCH"])
    @verify_oauth_token_auto
    @log_api_call
    def patch_resource_thumbnail(resource_id: str):
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.patch_resource_thumbnail(resource_id)

    @bp.route("/<resource_id>/address", methods=["GET"])
    @verify_oauth_token_auto
    @log_api_call
    def get_address(resource_id: str):
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.get_image_address(resource_id)

    @bp.route("/<resource_id>/<content_id>/exif", methods=["PATCH"])
    @verify_oauth_token_auto
    @log_api_call
    def patch_content_exif(resource_id: str, content_id: int):
        service = resource_service_map.get(resource_name)
        if not service:
            return make_response(
                jsonify(
                    {"status": "error", "message": f"Unknown resource: {resource_name}"}
                ),
                HTTPStatus.BAD_REQUEST,
            )
        return service.patch_content_exif(resource_id, content_id)

    return bp


# 各リソースの Blueprint を作成
books_bp = create_resource_blueprint("books")
videos_bp = create_resource_blueprint("videos")
music_bp = create_resource_blueprint("music")
documents_bp = create_resource_blueprint("documents")
images_bp = create_resource_blueprint("images")
