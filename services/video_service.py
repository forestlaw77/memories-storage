# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed for:
#   - Non-commercial use under the MIT License (see LICENSE-NC.txt)
#   - Commercial use requires a separate commercial license (contact author)
# You may not use this software for commercial purposes under the MIT License.

import logging
import subprocess
import tempfile
from http import HTTPStatus
from io import BytesIO
from typing import Dict, Optional, cast

import cv2
import numpy as np
from flask import request

from config.types import FULL_FILETYPE_MAP, FULL_MIMETYPE_MAP
from manager.video_processor import video_processor
from models.types import ResourceMeta
from services.base_service import BaseService


class VideoService(BaseService):
    def __init__(self, storage_backend):
        super().__init__(storage_backend, "videos")

    def _optional_thumbnail_process(
        self,
        content_id: int,
        resource_meta: ResourceMeta,
        content_buffer: Optional[BytesIO] = None,
    ) -> Optional[BytesIO]:
        """
        Extracts the first frame of the video and returns it as a thumbnail.

        Args:
            content_buffer (Optional[BytesIO]): Video content buffer.

        Returns:
            Optional[BytesIO]: Processed thumbnail content.
        """
        if content_id is None or resource_meta is None or content_buffer is None:
            return None

        try:
            basic_meta = resource_meta.get("basic_meta")
            contents = basic_meta.get("contents") if basic_meta else []
            existing_content = next(
                (
                    content
                    for content in contents
                    if int(content.get("id")) == content_id
                ),
                None,
            )
            if not existing_content:
                return None
            mimetype = existing_content.get("mimetype")
            suffix = f".{FULL_FILETYPE_MAP.get(mimetype, 'bin')}"
        except Exception as e:
            logging.error(f"[_optional_thumbnail_process] error: ({e})")
            return None

        # 一時ファイルに動画データを保存
        # コンテナの/tmpにvolumesで十分な大きさのメモリ・ファイルシステムを用意しておくこと
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
                tmp.write(content_buffer.getvalue())
                tmp.flush()
                video_path = tmp.name

                video = cv2.VideoCapture(video_path)
                if not video.isOpened():
                    logging.error(
                        f"[_optional_thumbnail_process] error: Failed to open video file {video_path}"
                    )
                    return None

                thumbnail_frame = None
                max_frames_to_check = 300  # 最大でチェックするフレーム数（例: 5秒間の動画なら30fpsで150フレーム）
                frame_count = 0
                brightness_threshold = 50  # 明るさのしきい値（0-255）
                best_brightness = 0
                fallback_frame = None

                while frame_count < max_frames_to_check:
                    success, frame = video.read()
                    if not success:
                        break  # 動画の終わりに達したか、フレームが読み込めない
                    if frame is None:
                        logging.error("Frame is None. Cannot convert to grayscale.")
                        continue

                    # フレームの明るさを計算
                    # ここではグレースケールに変換して平均ピクセル値を見る
                    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    gray_frame = cast(
                        np.ndarray, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    )
                    average_brightness = np.mean(gray_frame)

                    if average_brightness > best_brightness:
                        best_brightness = average_brightness
                        fallback_frame = frame

                    if average_brightness > brightness_threshold:
                        thumbnail_frame = frame
                        break  # 十分に明るいフレームが見つかった

                    frame_count += 1

                if thumbnail_frame is None and fallback_frame is not None:
                    thumbnail_frame = fallback_frame

                video.release()

                if thumbnail_frame is None:
                    logging.warning(
                        f"[_optional_thumbnail_process] Warning: No sufficiently bright frame found within the first {max_frames_to_check} frames for video {video_path}. Using the last checked frame if available."
                    )
                    video_reopen = cv2.VideoCapture(video_path)
                    _, thumbnail_frame = (
                        video_reopen.read()
                    )  # 再度最初のフレームを読み込む
                    video_reopen.release()
                    if thumbnail_frame is None:
                        logging.error("Failed to get any frame as fallback.")
                        return None

                _, img_encoded = cv2.imencode(".jpg", thumbnail_frame)
                thumbnail_buffer = BytesIO(img_encoded.tobytes())
        except Exception as e:
            logging.error(
                f"[_optional_thumbnail_process] error: Unexpected error ({e})"
            )
            return None

        return thumbnail_buffer

    def _optional_content_convert(
        self,
        resource_id: str,
        content_id: int,
        base_content: bytes,
        base_mimetype: str,
    ) -> Dict:
        """
        Converts video content if additional processing is required.

        Args:
            resource_id (str): The ID of the resource being processed.
            content_id (int): The ID of the specific content item.
            base_content (bytes): The raw binary content of the video.
            base_mimetype (str): The MIME type of the video content.

        Returns:
            dict: A structured response indicating whether the content was processed.
        """
        format = request.args.get("format", "").strip().lower()
        output_resolution = request.args.get("resolution", "").strip().lower()
        base_format = FULL_FILETYPE_MAP.get(base_mimetype, None)

        if not format or format == base_format:
            return self._generate_response_dict(
                status="success",
                message="Video content processed successfully.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.OK,
                data={"content": base_content, "mimetype": base_mimetype},
            )
        try:
            target_mimetype = FULL_MIMETYPE_MAP.get(format, None)
            if not target_mimetype or not base_format:
                raise ValueError(
                    f"Unsupported conversion: '{base_format}' to '{format}'."
                )
            result_content = video_processor.convert_video(
                format, base_content, base_mimetype, output_resolution
            )
        except ValueError as e:
            return self._generate_response_dict(
                status="error",
                message=f"Conversion to {format} is not supported.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.BAD_REQUEST,
                data=None,
            )
        except subprocess.CalledProcessError as e:
            return self._generate_response_dict(
                status="error",
                message=f"Video conversion to {format} failed.",
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                data=None,
            )
        except Exception as e:
            return self._generate_response_dict(
                status="error",
                message="Video processing failed.",
                error=str(e),
                resource_id=resource_id,
                content_id=content_id,
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                data=None,
            )

        return self._generate_response_dict(
            status="success",
            message="Video content processed successfully.",
            resource_id=resource_id,
            content_id=content_id,
            status_code=HTTPStatus.OK,
            data={"content": result_content, "mimetype": target_mimetype},
        )
