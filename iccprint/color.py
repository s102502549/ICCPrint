from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
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


def read_profile_info(path: str | Path) -> ProfileInfo:
    path = Path(path)
    profile = ImageCms.getOpenProfile(str(path))
    core = profile.profile
    description = _strip_icc_text(ImageCms.getProfileDescription(profile)) or path.name
    color_space = _strip_icc_text(getattr(core, "xcolor_space", ""))
    device_class = _strip_icc_text(getattr(core, "device_class", ""))

    supported: list[str] = []
    for label, intent in INTENTS.items():
        try:
            if ImageCms.isIntentSupported(profile, intent, ImageCms.Direction.OUTPUT) == 1:
                supported.append(label)
        except Exception:
            pass

    return ProfileInfo(
        path=path,
        description=description,
        color_space=color_space,
        device_class=device_class,
        supported_intents=tuple(supported),
    )


def _flatten_transparency(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        bg = Image.new("RGB", image.size, "white")
        bg.paste(image, mask=image.getchannel("A"))
        return bg
    if image.mode == "LA":
        rgba = image.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    if image.mode == "P" and "transparency" in image.info:
        rgba = image.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return image


def _source_profile_and_image(image: Image.Image, embedded_input_icc: Optional[bytes]):
    """Return (normalized image, source profile), falling back to sRGB."""
    image = _flatten_transparency(image)
    if embedded_input_icc and image.mode in {"RGB", "CMYK"}:
        try:
            return image, ImageCms.getOpenProfile(BytesIO(embedded_input_icc))
        except Exception:
            pass
    return image.convert("RGB"), ImageCms.createProfile("sRGB")


def convert_to_printer_rgb(
    image: Image.Image,
    output_profile_path: str | Path,
    intent: ImageCms.Intent,
    black_point_compensation: bool,
    embedded_input_icc: Optional[bytes] = None,
) -> Image.Image:
    """Convert an image to device RGB values using the selected printer ICC."""
    output_profile = ImageCms.getOpenProfile(str(output_profile_path))
    output_space = _strip_icc_text(getattr(output_profile.profile, "xcolor_space", ""))
    if output_space.upper() != "RGB":
        raise ValueError(
            f"目前版本支援 RGB 印表機描述檔；此描述檔的裝置色彩空間是 {output_space or '未知'}。"
        )

    if ImageCms.isIntentSupported(output_profile, intent, ImageCms.Direction.OUTPUT) != 1:
        raise ValueError("這個 ICC 描述檔不支援你選的 Rendering Intent。")

    flags = ImageCms.Flags.NONE
    if black_point_compensation:
        flags |= ImageCms.Flags.BLACKPOINTCOMPENSATION

    normalized, input_profile = _source_profile_and_image(image, embedded_input_icc)
    converted = ImageCms.profileToProfile(
        normalized,
        input_profile,
        output_profile,
        renderingIntent=intent,
        outputMode="RGB",
        flags=flags,
    )
    if converted is None:
        raise RuntimeError("ICC 色彩轉換失敗。")
    return converted


def softproof_to_srgb(
    image: Image.Image,
    printer_profile_path: str | Path,
    intent: ImageCms.Intent,
    black_point_compensation: bool,
    embedded_input_icc: Optional[bytes] = None,
) -> Image.Image:
    """Soft-proof the selected printer ICC to an sRGB preview.

    The selected user intent is used for the source -> proof-printer transform.
    The proof -> display transform uses Absolute Colorimetric, the usual soft-proof
    choice in LittleCMS. The final simulated printer result is converted to sRGB for display. This is
    an approximation: monitor calibration, ambient light and paper illumination
    still affect how closely the screen matches the physical print.
    """
    proof_profile = ImageCms.getOpenProfile(str(printer_profile_path))
    proof_space = _strip_icc_text(getattr(proof_profile.profile, "xcolor_space", ""))
    if proof_space.upper() != "RGB":
        raise ValueError(
            f"目前版本支援 RGB 印表機描述檔；此描述檔的裝置色彩空間是 {proof_space or '未知'}。"
        )
    if ImageCms.isIntentSupported(proof_profile, intent, ImageCms.Direction.OUTPUT) != 1:
        raise ValueError("這個 ICC 描述檔不支援你選的 Rendering Intent。")

    normalized, input_profile = _source_profile_and_image(image, embedded_input_icc)
    display_profile = ImageCms.createProfile("sRGB")
    flags = ImageCms.Flags.SOFTPROOFING
    if black_point_compensation:
        flags |= ImageCms.Flags.BLACKPOINTCOMPENSATION

    transform = ImageCms.buildProofTransform(
        input_profile,
        display_profile,
        proof_profile,
        normalized.mode,
        "RGB",
        # In LittleCMS/Pillow, renderingIntent is the source -> proof
        # (simulated printer) intent. proofRenderingIntent is the proof ->
        # display mapping; Absolute Colorimetric is the usual proofing choice.
        renderingIntent=intent,
        proofRenderingIntent=ImageCms.Intent.ABSOLUTE_COLORIMETRIC,
        flags=flags,
    )
    result = ImageCms.applyTransform(normalized, transform)
    if result is None:
        raise RuntimeError("ICC 軟打樣預覽失敗。")
    return result
