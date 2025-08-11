# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import os

# 運用時は下記のパラメータを適切に修正しなければならない
ALLOWED_ORIGINS = "*"  # os.getenv("ALLOWED_ORIGINS", "http://localhost")
FLASK_DEBUG = True  # os.getenv("FLASK_DEBUG", "False").lower() in ["true", "1"]
PORT = 4001

# リソースを保存するルートディレクトリ
STORAGE_DIRECTORY = os.getenv("STORAGE_DIRECTORY", "/local_storage")

# メタ情報をファイルシステムに保存する。(False: DB保存)
SAVE_META_IN_FILE_SYSTEM = True

# 拡張機能
## MP3 -> MIDI 変換機能の有効化 (toch等の追加パッケージが必要)
MP3_TO_MIDI_ENABLE = False
## 音の波形や周波数成分をもとにサムネイル作成 (librosa等の追加パッケージが必要)
SOUND_THUMBNAIL_ENABLE = False

## API Document 機能 (ビルトイン機能から削除予定)
SWAGGER_URL = "/api/docs"
SWAGGER_API_URL = "/swagger.json"


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
#     raise ValueError("Missing Google OAuth credentials in environment variables.")

# GOOGLE_OAUTH_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_OAUTH_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
MICROSOFT_OAUTH_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"
GITHUB_OAUTH_USERINFO_URL = "https://api.github.com/user"

PROVIDERS = {
    "google": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "authorize_url": "https://accounts.google.com/o/oauth2/auth",
        "access_token_url": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile",
    },
    "microsoft": {
        # "client_id": "YOUR_MICROSOFT_CLIENT_ID",
        "client_secret": "YOUR_MICROSOFT_CLIENT_SECRET",
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "access_token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "openid email profile",
    },
    "github": {
        # "client_id": "YOUR_GITHUB_CLIENT_ID",
        "client_secret": "YOUR_GITHUB_CLIENT_SECRET",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "access_token_url": "https://github.com/login/oauth/access_token",
        "scope": "user",
    },
}
