"""
renderer.py — product sketch image generator
Applies watercolor pencil sketch effect + transparent background removal.
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

_REMBG_SESSION = None


def _get_rembg_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        from rembg import new_session
        _REMBG_SESSION = new_session("birefnet-general")
    return _REMBG_SESSION


def remove_bg(img: Image.Image) -> Image.Image:
    """Background removal: corner-sample brightness + center weighting."""
    orig_lum = np.array(img.convert("L")).astype(np.float32)
    h_, w_ = orig_lum.shape
    margin = max(h_ // 10, w_ // 10, 20)
    corner_lum = np.mean([
        orig_lum[:margin, :margin].mean(),
        orig_lum[:margin, -margin:].mean(),
        orig_lum[-margin:, :margin].mean(),
        orig_lum[-margin:, -margin:].mean(),
    ])

    if corner_lum < 100:
        lum_alpha = np.clip((orig_lum - 25) * 6, 0, 255)
    else:
        lum_alpha = np.clip((248 - orig_lum) * 5, 0, 255)

    y_idx = np.arange(h_)[:, np.newaxis].astype(np.float32)
    x_idx = np.arange(w_)[np.newaxis, :].astype(np.float32)
    rel_y = np.abs(y_idx - h_ / 2) / (h_ / 2)
    rel_x = np.abs(x_idx - w_ / 2) / (w_ / 2)
    center_w = np.clip(1.0 - np.maximum(rel_y, rel_x) * 1.3, 0, 1)
    alpha = np.clip(lum_alpha + center_w * 90, 0, 255).astype(np.uint8)

    rgba = img.convert("RGBA")
    rgba.putalpha(Image.fromarray(alpha))
    return rgba


def sketch_effect(img_path: str) -> Image.Image:
    """
    Color watercolor + pencil sketch with transparent background.
    Returns RGBA image with product cutout on transparent bg.
    """
    img = Image.open(img_path).convert("RGB")

    # 1. Color watercolor base — keep 92% color
    soft = img.filter(ImageFilter.GaussianBlur(1.5))
    gray_rgb = soft.convert("L").convert("RGB")
    color_wash = Image.blend(soft, gray_rgb, 0.08)
    paper = np.array([255, 252, 247], dtype=np.float32)
    wash_arr = np.array(color_wash).astype(np.float32)
    base_arr = wash_arr * 0.88 + paper * 0.12

    # 2. Color-Dodge pencil sketch lines
    gray_l = img.convert("L")
    sharp = gray_l.filter(ImageFilter.UnsharpMask(radius=1.0, percent=150, threshold=1))
    sharp_arr = np.array(sharp).astype(np.float32)

    inv = 255.0 - sharp_arr
    blurred_inv = np.array(
        Image.fromarray(np.clip(inv, 0, 255).astype(np.uint8))
        .filter(ImageFilter.GaussianBlur(3.0))
    ).astype(np.float32)
    dodge = np.clip(sharp_arr * 255.0 / np.maximum(255.0 - blurred_inv, 1.0), 0, 255)
    line_strength = np.clip(1.0 - dodge / 255.0, 0, 1)
    line_strength = np.clip(line_strength ** 0.75, 0, 1)

    # 3. DoG edge reinforcement
    g1 = np.array(sharp.filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32)
    g2 = np.array(sharp.filter(ImageFilter.GaussianBlur(3.5))).astype(np.float32)
    dog = np.clip(np.abs(g1 - g2) * 3.0, 0, 255) / 255.0
    dog = np.clip(dog ** 0.70, 0, 1)

    combined = np.clip(line_strength * 0.70 + dog * 0.40, 0, 1)
    combined = np.array(
        Image.fromarray((combined * 255).astype(np.uint8))
        .filter(ImageFilter.GaussianBlur(0.4))
    ).astype(np.float32) / 255.0

    # 4. Apply pencil lines over color base
    pencil = np.array([38, 38, 58], dtype=np.float32)
    s = combined[..., np.newaxis]
    result_arr = base_arr * (1.0 - s * 0.82) + pencil * (s * 0.82)
    result_arr = np.clip(result_arr, 0, 255).astype(np.uint8)

    # 5. Paper texture noise
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 2.2, result_arr.shape).astype(np.float32)
    result_arr = np.clip(result_arr.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    result = Image.fromarray(result_arr)

    # 6. Background removal via birefnet neural net
    try:
        from rembg import remove as rembg_remove
        cutout = rembg_remove(img, session=_get_rembg_session())
        clean_a = cutout.split()[3]
        result_rgba = result.convert("RGBA")
        result_rgba.putalpha(clean_a)
        return result_rgba
    except Exception:
        result_rgba = result.convert("RGBA")
        alpha = Image.new("L", result_rgba.size, 220)
        result_rgba.putalpha(alpha)
        return result_rgba


def save_sketch(input_path: str, output_path: str) -> str:
    """Apply sketch effect and save as transparent PNG. Returns output_path."""
    print(f"[renderer] 스케치 효과 적용: {input_path}")
    sketch = sketch_effect(input_path)
    sketch.save(output_path, "PNG", optimize=True)
    print(f"[renderer] 저장 완료: {output_path}")
    return output_path
