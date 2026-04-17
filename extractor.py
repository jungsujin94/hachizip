"""
extractor.py — Claude API로 제품 메타 추출
scraper.js 결과에서 slug, 정제된 이름, 카테고리를 추출.
"""

import json
import os
import re
import anthropic
from dotenv import load_dotenv

load_dotenv()

CATEGORIES = ["소파", "침대", "테이블", "조명", "수납", "의자", "거울", "러그", "커튼", "기타"]

SYSTEM_PROMPT = """You are a product catalog assistant for a Korean furniture/home decor website.
Given raw scraped product data, return a clean JSON object with:
- slug: URL-safe English slug (lowercase, hyphens, max 6 words, descriptive)
- name_ko: cleaned Korean product name (remove store name, parenthetical notes, excess whitespace)
- name_en: short English product name or description (3-7 words, natural English)
- category: one of [소파, 침대, 테이블, 조명, 수납, 의자, 거울, 러그, 커튼, 기타]

Return ONLY valid JSON, no other text."""

USER_PROMPT_TEMPLATE = """Product data:
name: {name}
brand: {brand}
price: {price}
description: {description}

Return JSON with slug, name_ko, name_en, category."""


def extract_product_meta(scraped: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

    client = anthropic.Anthropic(api_key=api_key)

    prompt = USER_PROMPT_TEMPLATE.format(
        name=scraped.get("name", ""),
        brand=scraped.get("brand", ""),
        price=scraped.get("price", ""),
        description=(scraped.get("description", "") or "")[:300],
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        meta = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: derive slug from name
        name = scraped.get("name", "product")
        slug = re.sub(r"[^\w\s-]", "", name.lower())
        slug = re.sub(r"[\s_]+", "-", slug)[:60].strip("-")
        meta = {
            "slug": slug or "product",
            "name_ko": scraped.get("name", ""),
            "name_en": "",
            "category": "기타",
        }

    # Ensure slug is safe
    slug = meta.get("slug", "product")
    slug = re.sub(r"[^\w-]", "-", slug.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    meta["slug"] = slug or "product"

    return meta
