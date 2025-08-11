# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging
import os
import re
import unicodedata
from typing import Optional

import magic

from config.types import ALLOWED_FILE_MIME_TYPES


def get_mimetype(file) -> Optional[str]:
    """
    Gets the MIME type of a file.
    :param file: File object or file path
    :return: MIME type (e.g., "image/jpeg", "application/pdf")
    """
    mimetype = getattr(file, "mimetype", "application/octet-stream")
    if mimetype == "application/octet-stream":
        try:
            current_position = file.tell()
            file.seek(0)
            mime_detector = magic.Magic(mime=True)
            mimetype = mime_detector.from_buffer(file.read(2048))
            file.seek(current_position)
        except AttributeError:
            # Occurs if 'file' is a path and not a file-like object with .tell(), .seek(), .read()
            return None
        except ImportError:
            # Occurs if the 'python-magic' library is not installed
            logging.warning(
                "The 'python-magic' library is not installed. Cannot reliably determine MIME type."
            )
        except Exception as e:
            # Catch any other unexpected errors during MIME type detection
            logging.error(f"[get_mimetype] Error while determining the MIME type: {e}")
    return mimetype


def get_extension_from_mimetype(mimetype, file_category):
    """MIME タイプから拡張子を取得"""
    return ALLOWED_FILE_MIME_TYPES.get(file_category, {}).get(mimetype, "unknown")


def get_mimetype_from_extension(extension: str, file_category: str) -> str:
    """拡張子から MIME タイプを取得"""
    mime_types = {
        v: k for k, v in ALLOWED_FILE_MIME_TYPES.get(file_category, {}).items()
    }
    return mime_types.get(
        extension.lower(), "application/octet-stream"
    )  # 不明なら `octet-stream`


def sanitize_filename(filename: Optional[str]) -> Optional[str]:
    """
    ファイル名を安全な形式にサニタイズする。
    """
    if filename is None:
        return None

    # 1. ASCIIと一部の安全な記号以外の文字を削除
    #    Unicodeのカテゴリで制御文字 (Cc)、書式制御文字 (Cf)、サロゲート (Cs)、
    #    非公開領域 (Co, Cn) に該当する文字を削除
    filename = "".join(
        c
        for c in filename
        if unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn")
    )

    # 2. 安全な文字（英数字、ハイフン、アンダースコア、ピリオド）以外の文字を置換
    filename = re.sub(r"[^\w\-.]", "_", filename)

    # 3. 先頭や末尾のドットやアンダースコアを削除
    filename = filename.strip("._-")

    # 4. 連続するドットやアンダースコアを一つに置換
    filename = re.sub(r"([._-])+", r"\1", filename)

    # 5. ファイル名の長さを制限 (必要に応じて)
    max_length = 255  # 例
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        name = name[: max_length - len(ext) - 1]  # 拡張子と区切り文字の分を考慮
        filename = name + ext

    return filename
