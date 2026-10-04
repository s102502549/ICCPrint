from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from numbers import Integral
from typing import Optional

from PIL import Image, ImageCms


INTENTS = {
    "感應式 (Perceptual)": ImageCms.Intent.PERCEPTUAL,
    "相對比色 (Relative Colorimetric)": ImageCms.Intent.RELATIVE_COLORIMETRIC,
    "飽和度 (Saturation)": ImageCms.Intent.SATURATION,
    "絕對比色 (Absolute Colorimetric)": ImageCms.Intent.ABSOLUTE_COLORIMETRIC,
}


@dataclass(frozen=True)
class ProfileInfo:
    path: Path
    description: str
    color_space: str
    device_class: str
    supported_intents: tuple[str, ...]


def _strip_icc_text(value: object) -> str:
    return str(value or "").replace("\x00", "").strip()


def _profile_info(path: Path, profile: ImageCms.ImageCmsProfile) -> ProfileInfo:
    core = profile.profile
    description = _strip_icc_text(ImageCms.getProfileDescription(profile)) or path.name
    supported = tuple(
        label for label, intent in INTENTS.items()
        if ImageCms.isIntentSupported(profile, intent, ImageCms.Direction.OUTPUT) == 1
    )
    return ProfileInfo(
        path=path,
        description=description,
        color_space=_strip_icc_text(getattr(core, "xcolor_space", "")),
        device_class=_strip_icc_text(getattr(core, "device_class", "")),
        supported_intents=supported,
    )


def _profile_from_path(path: str | Path) -> ImageCms.ImageCmsProfile:
    """Load an owned memory profile without a Windows file handle.

    LittleCMS may keep a filename-backed ICC open for its entire lifetime.
    Tracebacks/transforms can prolong that lifetime after a failed operation,
    preventing temporary job directories from being removed on Windows.
    """
    with Path(path).open("rb") as source:
        data = source.read()
    return ImageCms.getOpenProfile(BytesIO(data))


def read_profile_info(path: str | Path) -> ProfileInfo:
    """Inspect an ICC profile without implying that it is a printer profile."""
    path = Path(path)
    return _profile_info(path, _profile_from_path(path))


def _open_printer_profile(
    path: str | Path,
    intent: Optional[ImageCms.Intent],
    *,
    allow_non_printer_profile: bool = False,
) -> ImageCms.ImageCmsProfile:
    try:
        profile = _profile_from_path(path)
    except (ImageCms.PyCMSError, OSError, TypeError, ValueError) as exc:
        raise ValueError("無法讀取印表機 ICC 描述檔，請選擇有效的 ICC / ICM 檔案。") from exc
    space = _strip_icc_text(getattr(profile.profile, "xcolor_space", "")).upper()
    if space != "RGB":
        raise ValueError(f"目前支援 RGB 印表機描述檔；此 ICC 的色彩空間是 {space or '未知'}。")
    device_class = _strip_icc_text(getattr(profile.profile, "device_class", "")).lower()
    if device_class != "prtr" and not allow_non_printer_profile:
        raise ValueError(
            f"此 ICC 的裝置類別是 {device_class or '未知'}，不是印表機輸出描述檔（prtr）。"
            "請選擇對應印表機、墨水與紙張的 RGB 輸出 ICC；螢幕 / sRGB 描述檔不能替代。"
        )
    if intent is not None:
        if isinstance(intent, bool) or not isinstance(intent, Integral) or intent not in tuple(INTENTS.values()):
            raise ValueError("Rendering Intent 必須是四種標準 ICC 意圖之一。")
        if ImageCms.isIntentSupported(profile, intent, ImageCms.Direction.OUTPUT) != 1:
            raise ValueError("這個 ICC 描述檔不支援你選的 Rendering Intent。")
    return profile


def validate_printer_profile(
    path: str | Path,
    intent: Optional[ImageCms.Intent] = None,
    *,
    allow_non_printer_profile: bool = False,
) -> ProfileInfo:
    """Require an RGB output-device ICC, optionally checking its rendering intent.

    ``allow_non_printer_profile`` is an explicit utility/testing escape hatch for
    matrix sRGB fixtures. Production printer selection must keep the default.
    """
    profile = _open_printer_profile(path, intent, allow_non_printer_profile=allow_non_printer_profile)
    return _profile_info(Path(path), profile)


def _flatten_transparency(image: Image.Image) -> Image.Image:
    """Return an owned, opaque image, compositing white in the source color space.

    In particular LA stays L until its gray ICC has been applied. Palette and
    keyed PNG transparency are expanded before removing alpha. Caller retains
    ownership of the input; all temporary channel images are closed here.
    """
    gray = image.mode in {"1", "L", "LA", "La"}
    alpha_mode = "LA" if gray else "RGBA"
    has_alpha = image.mode in {"RGBA", "RGBa", "LA", "La"} or (
        image.mode in {"RGB", "L", "1", "P"} and "transparency" in image.info
    )
    if has_alpha:
        expanded = image.convert(alpha_mode)
        channels = None
        background = None
        try:
            channels = expanded.getchannel("A")
            background = Image.new("L" if gray else "RGB", image.size, 255 if gray else "white")
            color = expanded.convert("L" if gray else "RGB")
            try:
                background.paste(color, mask=channels)
            finally:
                color.close()
            result, background = background, None
        finally:
            expanded.close()
            if channels is not None:
                channels.close()
            if background is not None:
                background.close()
    elif image.mode in {"P", "RGBX"}:
        result = image.convert("RGB")
    elif image.mode == "1":
        result = image.convert("L")
    else:
        result = image.copy()
    result.info = image.info.copy()
    result.info.pop("transparency", None)
    return result


def _source_profile_and_image(image: Image.Image, embedded_input_icc: Optional[bytes]):
    """Return an owned normalized image and a verified, matching source profile.

    An absent RGB/gray profile means sRGB. A present but corrupt or mismatched
    profile is an error, never a license to silently reinterpret the pixels.
    """
    expected_space = {
        "RGB": "RGB", "RGBA": "RGB", "RGBa": "RGB", "RGBX": "RGB", "P": "RGB",
        "L": "GRAY", "LA": "GRAY", "La": "GRAY", "1": "GRAY",
        "CMYK": "CMYK", "LAB": "LAB",
    }.get(image.mode)
    if expected_space is None:
        raise ValueError(
            f"不支援來源像素模式 {image.mode}。請在原程式轉存為 8-bit RGB 並嵌入正確的 ICC。"
        )
    embedded = embedded_input_icc if embedded_input_icc is not None else image.info.get("icc_profile")
    if embedded is not None:
        if not isinstance(embedded, (bytes, bytearray, memoryview)) or not embedded:
            raise ValueError("圖片內嵌 ICC 無效；請在原程式重新嵌入正確的來源 ICC 後再加入。")
        try:
            profile = ImageCms.getOpenProfile(BytesIO(bytes(embedded)))
        except (ImageCms.PyCMSError, OSError, TypeError, ValueError) as exc:
            raise ValueError("圖片內嵌 ICC 已損壞或無法讀取；請重新匯出並嵌入正確的來源 ICC。") from exc
        actual_space = _strip_icc_text(getattr(profile.profile, "xcolor_space", "")).upper()
        if actual_space != expected_space:
            raise ValueError(
                f"來源像素模式 {image.mode} 與內嵌 ICC 色彩空間 {actual_space or '未知'} 不相符。"
                "請在原程式指派正確的來源 ICC，或轉換為帶有 sRGB ICC 的 RGB 圖片。"
            )
    else:
        if expected_space in {"CMYK", "LAB"}:
            raise ValueError(
                f"{image.mode} 圖片沒有內嵌來源 ICC，無法安全判斷顏色。"
                "請在原程式嵌入正確的來源 ICC，或轉換為帶有 sRGB ICC 的 RGB 圖片。"
            )
        profile = ImageCms.createProfile("sRGB")

    normalized = _flatten_transparency(image)
    if embedded is None and normalized.mode != "RGB":
        try:
            rgb = normalized.convert("RGB")
        finally:
            normalized.close()
        normalized = rgb
    return normalized, profile


def source_to_srgb(image: Image.Image, embedded_input_icc: Optional[bytes] = None) -> Image.Image:
    """Color-manage an unproofed display image; never display device RGB directly."""
    normalized, input_profile = _source_profile_and_image(image, embedded_input_icc)
    try:
        result = ImageCms.profileToProfile(
            normalized,
            input_profile,
            ImageCms.createProfile("sRGB"),
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            outputMode="RGB",
            flags=ImageCms.Flags.BLACKPOINTCOMPENSATION,
        )
    finally:
        normalized.close()
    if result is None:
        raise RuntimeError("來源 ICC → sRGB 預覽轉換失敗。")
    return result


def convert_to_printer_rgb(
    image: Image.Image,
    output_profile_path: str | Path,
    intent: ImageCms.Intent,
    black_point_compensation: bool,
    embedded_input_icc: Optional[bytes] = None,
    *,
    allow_non_printer_profile: bool = False,
) -> Image.Image:
    """Convert source pixels to device RGB using a verified printer output ICC."""
    output_profile = _open_printer_profile(
        output_profile_path, intent, allow_non_printer_profile=allow_non_printer_profile,
    )
    flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if black_point_compensation else ImageCms.Flags.NONE
    normalized, input_profile = _source_profile_and_image(image, embedded_input_icc)
    try:
        converted = ImageCms.profileToProfile(
            normalized, input_profile, output_profile,
            renderingIntent=intent, outputMode="RGB", flags=flags,
        )
    finally:
        normalized.close()
    if converted is None:
        raise RuntimeError("ICC 色彩轉換失敗。")
    return converted


def softproof_to_srgb(
    image: Image.Image,
    printer_profile_path: str | Path,
    intent: ImageCms.Intent,
    black_point_compensation: bool,
    embedded_input_icc: Optional[bytes] = None,
    *,
    allow_non_printer_profile: bool = False,
) -> Image.Image:
    """Simulate the printer on sRGB, retaining the selected source-to-proof intent.

    Proof-to-display uses Absolute Colorimetric to simulate paper white. This
    remains an approximation on an uncalibrated display and is not a measured
    paper/ink match. Source alpha is flattened onto white before ICC conversion.
    """
    proof_profile = _open_printer_profile(
        printer_profile_path, intent, allow_non_printer_profile=allow_non_printer_profile,
    )
    normalized, input_profile = _source_profile_and_image(image, embedded_input_icc)
    flags = ImageCms.Flags.SOFTPROOFING
    if black_point_compensation:
        flags |= ImageCms.Flags.BLACKPOINTCOMPENSATION
    try:
        display_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        transform = ImageCms.buildProofTransform(
            input_profile, display_profile, proof_profile, normalized.mode, "RGB",
            renderingIntent=intent,
            proofRenderingIntent=ImageCms.Intent.ABSOLUTE_COLORIMETRIC,
            flags=flags,
        )
        result = ImageCms.applyTransform(normalized, transform)
        if result is None:
            raise RuntimeError("ICC 軟打樣預覽失敗。")
        # applyTransform does not guarantee destination-profile metadata on all
        # Pillow versions. Never let a display image retain the printer/source ICC.
        result.info["icc_profile"] = display_profile.tobytes()
        return result
    finally:
        normalized.close()
