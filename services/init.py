# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

from typing import Type

from manager.document_processor import DocumentProcessor
from manager.image_processor import ImageProcessor
from services.book_service import BookService
from services.document_service import DocumentService
from services.image_service import ImageService
from services.music_service import MusicService
from services.video_service import VideoService
from storage.abstract_backend import AbstractStorageBackend

# from storage.local_backend import LocalStorageBackend
# from storage.local_json_backend import LocalStorageJsonBackend
from storage.local_bare_backend import LocalStorageBareBackend

# from config.settings import CURRENT_STORAGE, STORAGE_TYPE


# ストレージの種類を `settings.py` に基づいて選択
# if CURRENT_STORAGE == STORAGE_TYPE.LOCAL_JSON:
#     storage_backend = LocalStorageJsonBackend()
# elif CURRENT_STORAGE == STORAGE_TYPE.LOCAL_FILE:
#     storage_backend = LocalStorageBackend()
# else:
#     raise ValueError(f"Unsupported storage type: {CURRENT_STORAGE}")
storage_backend: AbstractStorageBackend = LocalStorageBareBackend()

# 各サービスのインスタンス化を `services/init.py` に統合
book_service = BookService(storage_backend)
document_service = DocumentService(storage_backend)
image_service = ImageService(storage_backend)
music_service = MusicService(storage_backend)
video_service = VideoService(storage_backend)

# 各リソースと対応するサービスオブジェクトを辞書で管理
resource_service_map = {
    "books": book_service,
    "videos": video_service,
    "music": music_service,
    "documents": document_service,
    "images": image_service,
}
