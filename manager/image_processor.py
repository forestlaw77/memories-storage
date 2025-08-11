# Copyright (c) 2025 Tsutomu FUNADA
# This software is licensed under the MIT License for non-commercial use.

import json
import logging
import os
import subprocess
import tempfile
from io import BytesIO, IOBase
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict, Union

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from werkzeug.datastructures import FileStorage

from config.types import FULL_FILETYPE_MAP, ImageFitMode


class ImageProcessor:
    def __init__(self):
        register_heif_opener()

    def _save_input_to_temp_file(
        self, src_input: Union[FileStorage, IOBase], suffix: Optional[str] = None
    ) -> str:
        """
        FileStorage または BytesIO オブジェクトを一時ファイルに保存し、そのパスを返す。
        一時ファイルは delete=False で作成される。
        呼び出し元でファイルの削除責任を負う必要がある。
        """

        try:
            suffix = f".{suffix.lstrip('.')}" if suffix else ""

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                if isinstance(src_input, FileStorage):
                    src_input.stream.seek(0)
                    temp_file.write(src_input.stream.read())
                elif isinstance(src_input, IOBase):
                    src_input.seek(0)
                    temp_file.write(src_input.read())
                else:
                    raise TypeError(
                        "Unsupported input type for temporary file creation."
                    )
                return temp_file.name
        except Exception as e:
            logging.error(f"Error creating temporary file: {e}")
            raise RuntimeError(f"Failed to create temporary file from input: {e}")

    def convert_image(
        self,
        src_path: Union[str, Path, FileStorage, BytesIO],
        dest_path: str,
        format: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        quality: int = 85,
        fit_mode: ImageFitMode = ImageFitMode.CONTAIN,
        keep_exif: bool = False,
    ) -> str:
        """
        Convert an image to the specified format and resize it based on `fit_mode`.
        Optionally, preserve EXIF metadata if requested.

        :param src_path: Source image file path
        :param dest_path: Destination file path where converted image will be saved
        :param format: Target format (e.g., 'JPEG', 'PNG', 'WEBP', 'BMP', etc.)
        :param width: Desired width of the bounding box (optional)
        :param height: Desired height of the bounding box (optional)
        :param quality: JPEG compression quality (default: 85)
        :param fit_mode: How the image should fit within the bounding box
                         (ImageFitMode.CONTAIN or ImageFitMode.COVER)
        :param keep_exif: Whether to retain EXIF metadata (only for supported formats)
        :return: Path to the converted image
        """

        dest_format = format.upper() if format else None
        try:
            if isinstance(src_path, FileStorage):
                src_path.stream.seek(0)
                image = Image.open(src_path.stream)
            else:
                image = Image.open(src_path)

            if not image.format:
                raise ValueError(
                    "Failed to detect image format. The input might be corrupted."
                )
            src_format = image.format.upper()
            dest_format = (
                dest_format or src_format
            )  # format is optional, use source format if not specified

            keep_exif = (
                keep_exif
                and src_format in ["JPEG", "MPO", "TIFF", "HEIC"]
                and dest_format in ["JPEG", "TIFF", "HEIC"]
            )

            # Determine if we should transpose the image based on EXIF orientation
            should_transpose = not keep_exif and src_format in [
                "JPEG",
                "MPO",
                "TIFF",
                "HEIC",
            ]

            # ソースがorientationを持っていて、変換後にorientationを失う場合は、回転しておく
            if should_transpose:
                image = ImageOps.exif_transpose(image)
            original_width, original_height = image.size

            if width or height:
                width = width or original_width
                height = height or original_height

                new_width, new_height = self._calculate_resized_dimensions(
                    original_width, original_height, width, height, fit_mode
                )

                resized_img = image.resize((new_width, new_height), Image.LANCZOS)  # type: ignore

                if fit_mode == ImageFitMode.COVER:
                    left = int((new_width - width) / 2)
                    top = int((new_height - height) / 2)
                    right = int((new_width + width) / 2)
                    bottom = int((new_height + height) / 2)
                    resized_img = resized_img.crop((left, top, right, bottom))
            else:
                resized_img = image

            class SaveKwargs(TypedDict, total=False):
                format: str
                quality: int
                lossless: bool

            save_kwargs: SaveKwargs = {"format": dest_format}
            if dest_format in ["JPEG", "WEBP"]:
                save_kwargs["quality"] = quality
            elif dest_format == "HEIC":
                save_kwargs["lossless"] = True  # HEIC supports lossless compression

            resized_img.save(dest_path, **save_kwargs)

            # Preserve EXIF metadata if requested
            if keep_exif:
                exif_src_path = None
                try:
                    if isinstance(src_path, (str, Path)):
                        exif_src_path = str(src_path)
                    else:
                        # Save the source image to a temporary file for EXIF extraction
                        exif_src_path = self._save_input_to_temp_file(
                            src_path, suffix=f".{src_format.lower()}"
                        )
                    subprocess.run(
                        [
                            "exiftool",
                            "-TagsFromFile",
                            exif_src_path,
                            "-all:all",
                            "-unsafe",
                            dest_path,
                        ],
                        check=True,
                    )
                except FileNotFoundError:
                    logging.warning("ExifTool is not available. Skipping EXIF copy.")
                finally:
                    if not isinstance(src_path, (str, os.PathLike)) and exif_src_path:
                        try:
                            os.remove(exif_src_path)
                        except OSError as e:
                            logging.warning(
                                f"Failed to remove temporary EXIF file: {e}"
                            )

            logging.info(
                f"Image converted: {src_path} -> {dest_path} ({dest_format}, width={width}, height={height}, quality={quality}, fit_mode={fit_mode})"
            )
            return dest_path

        except subprocess.CalledProcessError as e:
            logging.error(f"ExifTool failed: {e.stderr}")
            raise RuntimeError(f"ExifTool processing error: {e}") from e
        except Exception as e:
            logging.error(f"Error converting image {src_path} to {dest_format}: {e}")
            raise

    def _calculate_resized_dimensions(
        self,
        original_width: int,
        original_height: int,
        target_width: int,
        target_height: int,
        fit_mode: ImageFitMode,
    ) -> tuple[int, int]:
        """
        Calculate the resized dimensions of an image while maintaining aspect ratio
        based on the specified fit mode ('ImageFitMode.CONTAIN' or 'ImageFitMode.COVER').

        :param original_width: Width of the original image
        :param original_height: Height of the original image
        :param target_width: Desired width of the bounding box
        :param target_height: Desired height of the bounding box
        :param fit_mode: Resizing mode ('ImageFitMode.CONTAIN' keeps the full image, 'ImageFitMode.COVER' fills the space)
        :return: Tuple containing the new width and height of the resized image
        """
        # Calculate the original aspect ratio
        aspect_ratio = original_width / original_height
        container_aspect_ratio = target_width / target_height

        # Fit mode: 'contain' -> Scale down while keeping the full image within bounds
        if fit_mode == ImageFitMode.CONTAIN:
            if aspect_ratio > container_aspect_ratio:
                # Image is wider than target → Adjust width, scale height accordingly
                new_width = target_width
                new_height = int(new_width / aspect_ratio)
            else:
                # Image is taller than target → Adjust height, scale width accordingly
                new_height = target_height
                new_width = int(new_height * aspect_ratio)

        # Fit mode: 'cover' -> Scale up to completely fill the space, cropping excess parts
        elif fit_mode == ImageFitMode.COVER:
            if aspect_ratio > container_aspect_ratio:
                # Image is wider than target → Adjust height, scale width accordingly
                new_height = target_height
                new_width = int(new_height * aspect_ratio)
            else:
                # Image is taller than target → Adjust width, scale height accordingly
                new_width = target_width
                new_height = int(new_width / aspect_ratio)

        else:
            # Invalid fit_mode → Raise an error
            raise ValueError(f"Invalid fit_mode: {fit_mode}")

        return int(new_width), int(new_height)

    def extract_exif(
        self,
        image_file: Union[str, BytesIO, FileStorage, Path],
        mimetype: Optional[str] = None,
    ) -> Dict[str, Any]:
        # logging.info("[extract_exif]extract exif process starting...")

        file_path_to_use = None  # exiftoolに渡すパス
        temp_file_created = (
            False  # _save_input_to_temp_file で一時ファイルが作成されたか
        )

        try:
            # If image_file is a file path, use it directly
            if isinstance(image_file, (str, Path)):
                file_path_to_use = str(image_file)
            # If image_file is BytesIO or FileStorage, save it as a temporary file
            else:
                suffix = FULL_FILETYPE_MAP.get(mimetype, "bin") if mimetype else "bin"
                # 共通化されたヘルパーメソッドを呼び出す
                file_path_to_use = self._save_input_to_temp_file(image_file, suffix)
                temp_file_created = True  # 一時ファイルが作成されたフラグ

            # Run ExifTool to extract metadata in JSON format
            process = subprocess.run(
                [
                    "exiftool",
                    "-json",
                    "-c",
                    "%+.6f",
                    "-d",
                    "%Y-%m-%dT%H:%M:%S",
                    file_path_to_use,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            metadata = json.loads(process.stdout)[0]
            # Filter out unwanted keys
            EXCLUDE_KEYS: set[str] = {"SourceFile", "Directory", "FilePermissions"}
            filtered_metadata = {
                k: v for k, v in metadata.items() if k not in EXCLUDE_KEYS
            }

            return filtered_metadata

        except subprocess.CalledProcessError as e:
            logging.error(
                f"[extract_exif] ExifTool Error - Return Code: {e.returncode}, Output: {e.stderr}"
            )
            return {}

        except Exception as e:
            logging.error(
                f"[extract_exif] Unexpected error extracting EXIF data: {type(image_file)}, Error: {e}"
            )
            return {}

        finally:
            # ヘルパーメソッドで一時ファイルが作成された場合のみ削除
            if temp_file_created and file_path_to_use:
                try:
                    os.remove(file_path_to_use)
                except OSError as e:
                    logging.warning(f"Failed to remove temporary EXIF file: {e}")

    def update_exif(
        self,
        image_file: Union[str, BytesIO, FileStorage, Path],
        mimetype: Optional[str],
        update_items: Dict[str, Any],
    ) -> Union[bool, BytesIO]:
        """
        Updates selective Exif metadata fields of the image.

        Parameters:
        - image_file: Input image source
        - mimetype: MIME type of the image
        - update_items: Dictionary of Exif tag → new value

        Returns:
        - BytesIO: If the input was BytesIO or FileStorage, returns the updated image as BytesIO.
        - True: If the input was a file path and the update succeeded.
        - False: If the update failed
        """
        # logging.info("[updatet_exif]update exif process starting...")

        def build_exiftool_args(update_items: Dict[str, Any]) -> List[str]:
            """
            Converts key-value pairs into ExifTool command-line arguments.

            Example:
                {"Orientation": 1, "ImageDescription": "My photo"}
                → ['-Orientation=1', '-ImageDescription=My photo']
            """
            args = []
            for key, value in update_items.items():
                if isinstance(value, (str, int, float)):
                    args.append(f"-{key}={value}")
                else:
                    logging.warning(
                        f"[build_exiftool_args] Unsupported value for key '{key}': {value}"
                    )
            return args

        file_path_to_use = None  # exiftoolに渡すパス
        temp_file_created = (
            False  # _save_input_to_temp_file で一時ファイルが作成されたか
        )

        try:
            # If image_file is a file path, use it directly
            if isinstance(image_file, (str, Path)):
                file_path_to_use = str(image_file)
            # If image_file is BytesIO or FileStorage, save it as a temporary file
            else:
                suffix = FULL_FILETYPE_MAP.get(mimetype, "bin") if mimetype else "bin"
                # 共通化されたヘルパーメソッドを呼び出す
                file_path_to_use = self._save_input_to_temp_file(image_file, suffix)
                temp_file_created = True  # 一時ファイルが作成されたフラグ

            args = ["-tagsFromFile", "@"] + build_exiftool_args(update_items)

            # Run ExifTool to extract metadata in JSON format
            process = subprocess.run(
                ["exiftool", "-overwrite_original"] + args + [file_path_to_use],
                check=True,
            )

            if temp_file_created:
                with open(file_path_to_use, "rb") as f:
                    return BytesIO(f.read())

            return True

        except subprocess.CalledProcessError as e:
            logging.error(
                f"[update_exif] ExifTool Error - Return Code: {e.returncode}, Output: {e.stderr}"
            )
            return False

        except Exception as e:
            logging.error(
                f"[update_exif] Unexpected error extracting EXIF data: {type(image_file)}, Error: {e}"
            )
            return False

        finally:
            # ヘルパーメソッドで一時ファイルが作成された場合のみ削除
            if temp_file_created and file_path_to_use:
                try:
                    os.remove(file_path_to_use)
                except OSError as e:
                    logging.warning(f"Failed to remove temporary EXIF file: {e}")

    def rotate_image(
        self, target: bytes, angle: int, format: Optional[str] = None
    ) -> bytes:
        # EXIFのOrientationに基づいて正しい向きに補正
        image = Image.open(BytesIO(target))
        image = ImageOps.exif_transpose(image)

        # 回転処理（時計回り）
        rotated = image.rotate(-angle, expand=True)

        # モード変換：Pや1など保存できない形式を避ける
        if rotated.mode in ("P", "1"):
            rotated = rotated.convert("RGB")

        # フォーマットを明確にする
        final_format = format or image.format
        if not final_format:
            raise ValueError(
                "Cannot determine image format. Please specify 'format' explicitly."
            )

        # バッファへ保存
        buffer = BytesIO()
        rotated.save(buffer, format=final_format)
        return buffer.getvalue()


image_processor = ImageProcessor()
