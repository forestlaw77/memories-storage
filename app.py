# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging

import requests
from authlib.integrations.flask_client import OAuth
from flask import Flask, g, jsonify, request, url_for
from flask_cors import CORS

from auth.verify_auth_token import verify_oauth_token
from config.settings import ALLOWED_ORIGINS, FLASK_DEBUG, PORT, PROVIDERS

# Initialize Flask application
app = Flask(__name__)

# Enable Cross-Origin Resource Sharing (CORS)
CORS(
    app,
    supports_credentials=True,
    resources={
        r"/*": {
            "origins": "http://localhost:8080",
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }
    },
)

# OAuth Setup
oauth = OAuth(app)
for provider, config in PROVIDERS.items():
    if not config.get("client_id") or not config.get("client_secret"):
        continue  # 不完全な設定をスキップ
    oauth.register(
        provider,
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        authorize_url=config["authorize_url"],
        access_token_url=config["access_token_url"],
        client_kwargs={"scope": config["scope"]},
    )


@app.route("/login/<provider>")
def login(provider):
    """OAuth プロバイダーごとにログイン処理"""
    if provider not in PROVIDERS.keys():
        return jsonify({"error": "Invalid provider"}), 400

    client = oauth.create_client(provider)
    if not client:
        return jsonify({"error": f"OAuth client for '{provider}' not found"}), 400
    return client.authorize_redirect(
        url_for("auth_callback", provider=provider, _external=True)
    )


@app.route("/auth/callback/<provider>")
def auth_callback(provider):
    """OAuth 認証後のコールバック処理"""
    try:
        client = oauth.create_client(provider)
        if not client:
            return jsonify({"error": f"Failed to create client for {provider}"}), 500

        token = client.authorize_access_token()
        if not token:
            return jsonify({"error": "Token retrieval failed"}), 401

        if provider == "github":
            headers = {"Authorization": f"Bearer {token['access_token']}"}
            user_info = requests.get(
                "https://api.github.com/user", headers=headers
            ).json()

            # GitHub は `email` を取得するため追加リクエストが必要
            email_response = requests.get(
                "https://api.github.com/user/emails", headers=headers
            )
            if email_response.status_code == 200:
                emails = email_response.json()
                primary_email = next(
                    (email["email"] for email in emails if email["primary"]), None
                )
                user_info["email"] = primary_email

        else:
            user_info = client.parse_id_token(token)

        if not user_info:
            return jsonify({"error": "User info parsing failed"}), 401

        return jsonify(
            {"message": f"Authenticated via {provider}", "user_info": user_info}
        )

    except Exception as e:
        return jsonify({"error": f"Authentication failed: {str(e)}"}), 500


# @app.after_request
# def handle_cors_headers(response):
#     # すべてのリクエストに対して共通のヘッダーを設定
#     response.headers["Access-Control-Allow-Origin"] = "http://localhost:8080"
#     response.headers["Access-Control-Allow-Credentials"] = "true"  # ★ここが重要★

#     # プリフライトリクエスト (OPTIONS) の場合の追加ヘッダー
#     if request.method == "OPTIONS":
#         # ブラウザが本番リクエストで許可を求めるメソッド
#         # リクエストヘッダーから Access-Control-Request-Method を読み取るのがベスト
#         allowed_methods = request.headers.get(
#             "Access-Control-Request-Method", "GET, POST, PUT, PATCH, DELETE, OPTIONS"
#         )
#         response.headers["Access-Control-Allow-Methods"] = allowed_methods

#         # ブラウザが本番リクエストで許可を求めるヘッダー
#         # リクエストヘッダーから Access-Control-Request-Headers を読み取るのがベスト
#         allowed_headers = request.headers.get(
#             "Access-Control-Request-Headers", "Content-Type, Authorization"
#         )
#         response.headers["Access-Control-Allow-Headers"] = allowed_headers

#         # プリフライトリクエストの有効期間 (秒)
#         response.headers["Access-Control-Max-Age"] = "86400"  # 24時間

#         # プリフライトリクエストの場合は204 No Contentを返す
#         # @app.route("/", methods=["OPTIONS"]) のような個別のハンドラがなければこれで対応できる
#         # ただし、ハンドラがある場合はそちらが優先される
#         if (
#             response.status_code == 405
#         ):  # もしOPTIONSに対するデフォルトの405 Method Not Allowedが返された場合
#             return "", 204  # ここで明示的に204を返す

#     return response


# Blueprint の登録
from api.health import health_bp
from api.resource_api import books_bp, documents_bp, images_bp, music_bp, videos_bp
from api.users_api import users_bp

app.register_blueprint(users_bp, url_prefix="/v1/users")
app.register_blueprint(health_bp, url_prefix="/v1")
app.register_blueprint(books_bp, url_prefix="/v1/books")
app.register_blueprint(documents_bp, url_prefix="/v1/documents")
app.register_blueprint(images_bp, url_prefix="/v1/images")
app.register_blueprint(music_bp, url_prefix="/v1/music")
app.register_blueprint(videos_bp, url_prefix="/v1/videos")

# Logging 設定
logging.basicConfig(level=logging.INFO)

# Flask アプリの起動
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=FLASK_DEBUG)
