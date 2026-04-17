"""
pipeline.py — productspage main entry point

Usage:
  python pipeline.py https://www.ohou.se/products/XXXXX
  python pipeline.py https://www.coupang.com/vp/products/XXXXX
  python pipeline.py --ohouse URL --coupang URL
"""

import sys
import json
import subprocess
import tempfile
import os
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from io import BytesIO

from renderer import save_sketch, remove_bg
from extractor import extract_product_meta
from page import generate_page

PRODUCTS_DIR = Path("products")
PRODUCTS_JSON = Path("products.json")


def resolve_url(url: str) -> str:
    """Follow redirects to get the final URL (handles URL shorteners)."""
    if "ohou.se" in url or "coupang.com" in url:
        return url
    try:
        r = requests.get(url, allow_redirects=True, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        final = r.url
        print(f"[pipeline] URL 리다이렉트: {url} → {final}")
        return final
    except Exception:
        return url


def scrape(url: str) -> dict:
    result = subprocess.run(
        ["node", "scraper.js", url],
        capture_output=True, cwd=Path(__file__).parent
    )
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    if result.returncode != 0:
        err = stderr.strip()
        try:
            err = json.loads(err).get("error", err)
        except Exception:
            pass
        raise RuntimeError(f"Scraper 오류: {err}")
    return json.loads(stdout)


def download_image(url: str, dest: Path) -> bool:
    try:
        r = requests.get(
            url, timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"[pipeline] 이미지 다운로드 실패: {e}")
        return False


def _score_image(url: str) -> tuple[float, bytes]:
    """
    Download and score an image URL for product-sketch suitability.
    Returns (score, raw_bytes). Higher score = better candidate.

    Criteria:
      - fill_ratio: how much of the frame the product occupies (more = better)
      - center_score: how close the product centroid is to the image center
      - bg_simplicity: how uniform the background is (low variance = simpler)
    """
    try:
        r = requests.get(url, timeout=12,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        raw = r.content
        img = Image.open(BytesIO(raw)).convert("RGB")
        img.thumbnail((256, 256))  # fast scoring on small copy

        rgba = remove_bg(img)
        alpha = np.array(rgba.split()[3]).astype(np.float32)
        h, w = alpha.shape
        mask = alpha > 128

        product_px = mask.sum()
        if product_px == 0:
            return 0.0, raw

        # 1. Fill ratio — product pixels / total pixels
        fill_ratio = product_px / (h * w)

        # 2. Center score — product centroid distance from image center
        y_idx, x_idx = np.mgrid[0:h, 0:w]
        cy = np.average(y_idx, weights=mask)
        cx = np.average(x_idx, weights=mask)
        dist = ((cy - h / 2) ** 2 + (cx - w / 2) ** 2) ** 0.5
        max_dist = ((h / 2) ** 2 + (w / 2) ** 2) ** 0.5
        center_score = 1.0 - (dist / max_dist)

        # 3. Background simplicity — low std-dev of non-product pixels = cleaner bg
        bg_pixels = np.array(img)[~mask]
        bg_std = bg_pixels.std() if len(bg_pixels) > 0 else 255.0
        bg_simplicity = 1.0 - min(bg_std / 80.0, 1.0)  # 80 std = complex scene

        score = fill_ratio * 0.55 + center_score * 0.25 + bg_simplicity * 0.20
        return score, raw
    except Exception:
        return 0.0, b""


def pick_best_image(img_urls: list, max_candidates: int = 4):
    """Score up to max_candidates URLs and return raw bytes of the best one."""
    candidates = [u for u in img_urls if u][:max_candidates]
    if not candidates:
        return None

    print(f"[pipeline] 이미지 {len(candidates)}장 평가 중...")
    scores = []
    raws = []
    for i, url in enumerate(candidates):
        score, raw = _score_image(url)
        scores.append(score)
        raws.append(raw)
        print(f"[pipeline]   [{i}] score={score:.3f}  {url[:60]}...")

    best = int(np.argmax(scores))
    print(f"[pipeline] 최적 이미지: [{best}] (score={scores[best]:.3f})")
    return raws[best] if raws[best] else None


def load_products() -> list:
    if PRODUCTS_JSON.exists():
        with open(PRODUCTS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_products(products: list):
    PRODUCTS_JSON.write_text(
        json.dumps(products, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def main():
    args = sys.argv[1:]
    ohouse_url = None
    coupang_url = None

    if "--ohouse" in args:
        idx = args.index("--ohouse")
        ohouse_url = args[idx + 1]
    if "--coupang" in args:
        idx = args.index("--coupang")
        coupang_url = args[idx + 1]

    if not ohouse_url and not coupang_url:
        if not args:
            print("사용법:")
            print("  python pipeline.py [URL]")
            print("  python pipeline.py --ohouse URL --coupang URL")
            sys.exit(1)
        url = args[0]
        if "coupang" in url:
            coupang_url = url
        else:
            ohouse_url = url

    # Resolve shortened URLs
    if ohouse_url:
        ohouse_url = resolve_url(ohouse_url)
    if coupang_url:
        coupang_url = resolve_url(coupang_url)

    # Scrape primary URL
    primary_url = ohouse_url or coupang_url
    print(f"[pipeline] 스크래핑 중: {primary_url}")
    data = scrape(primary_url)
    print(f"[pipeline] 제품명: {data.get('name', '(unknown)')}")
    print(f"[pipeline] 가격: {data.get('price', '(unknown)')}")

    # Optionally scrape secondary URL for price comparison
    secondary_data = None
    if ohouse_url and coupang_url:
        secondary_url = coupang_url if primary_url == ohouse_url else ohouse_url
        print(f"[pipeline] 보조 스크래핑 중: {secondary_url}")
        try:
            secondary_data = scrape(secondary_url)
            print(f"[pipeline] 보조 가격: {secondary_data.get('price', '(unknown)')}")
        except Exception as e:
            print(f"[pipeline] 보조 스크래핑 실패 (계속 진행): {e}")

    # Extract clean meta via Claude
    print("[pipeline] 메타 추출 중 (Claude API)...")
    meta = extract_product_meta(data)
    slug = meta["slug"]
    print(f"[pipeline] slug: {slug}")
    print(f"[pipeline] 카테고리: {meta.get('category', '기타')}")

    # Download first product image and apply sketch effect
    PRODUCTS_DIR.mkdir(exist_ok=True)
    img_urls = data.get("imageUrls", [])
    sketch_path = PRODUCTS_DIR / f"{slug}.png"

    if img_urls:
        best_bytes = pick_best_image(img_urls)
        if best_bytes:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                tmp_path.write_bytes(best_bytes)
                save_sketch(str(tmp_path), str(sketch_path))
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            sketch_path = None
    else:
        sketch_path = None
        print("[pipeline] 제품 이미지 URL을 찾지 못했습니다.")

    # Assign prices per site
    ohouse_price = ""
    coupang_price = ""
    if data.get("site") == "ohou" or ohouse_url and not coupang_url:
        ohouse_price = data.get("price", "")
        if secondary_data:
            coupang_price = secondary_data.get("price", "")
    else:
        coupang_price = data.get("price", "")
        if secondary_data:
            ohouse_price = secondary_data.get("price", "")

    product = {
        "slug": slug,
        "name_ko": meta.get("name_ko") or data.get("name", ""),
        "name_en": meta.get("name_en", ""),
        "brand": data.get("brand", ""),
        "category": meta.get("category", "기타"),
        "image": f"products/{slug}.png" if sketch_path else "",
        "ohouse_url": ohouse_url or "",
        "coupang_url": coupang_url or "",
        "ohouse_price": ohouse_price,
        "coupang_price": coupang_price,
    }

    # Upsert into products.json
    products = load_products()
    existing_idx = next(
        (i for i, p in enumerate(products) if p["slug"] == slug), None
    )
    if existing_idx is not None:
        products[existing_idx].update(product)
        print(f"[pipeline] 기존 제품 업데이트: {slug}")
    else:
        products.append(product)
        print(f"[pipeline] 새 제품 추가: {slug}")

    save_products(products)
    print(f"[pipeline] products.json 저장 완료 ({len(products)}개 제품)")

    # Regenerate HTML
    print("[pipeline] index.html 생성 중...")
    generate_page(products)
    print("[pipeline] 완료! → index.html")


if __name__ == "__main__":
    main()
