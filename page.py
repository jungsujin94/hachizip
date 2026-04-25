"""
page.py — Generates index.html product catalog from products.json.

Usage:
  python page.py          # reads products.json, writes index.html
  python page.py --regen  # same (alias kept for consistency)
"""

import json
import sys
from pathlib import Path
from PIL import Image

PRODUCTS_JSON = Path("products.json")
OUTPUT_HTML = Path("index.html")
CATALOG_TITLE = "hachizip items"
DISCLAIMER_OHOUSE  = "이 포스팅은 오늘의집 큐레이터 활동의 일환으로, 구매시 이에 따른 일정액의 수수료를 제공받습니다."
DISCLAIMER_COUPANG = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
DISCLAIMER_PRICE   = "※ 표시된 가격은 쿠폰 적용 전 가격이며, 배송비가 별도로 발생할 수 있습니다."


def make_sticker_nobg():
    """Strip white background from newsticker.png → save newsticker_nobg.png."""
    src = Path("images/newsticker.png")
    dst = Path("images/newsticker_nobg.png")
    if not src.exists():
        return
    img = Image.open(src).convert("RGBA")
    pixels = img.getdata()
    new_pixels = []
    for r, g, b, a in pixels:
        # Treat near-white as transparent
        if r > 200 and g > 200 and b > 200:
            new_pixels.append((r, g, b, 0))
        else:
            new_pixels.append((r, g, b, a))
    img.putdata(new_pixels)
    img.save(dst, format="PNG")


def build_card(p: dict, order: int = 0, is_new: bool = False) -> str:
    slug         = p.get("slug", "")
    img          = p.get("image", "")
    name_ko      = p.get("name_ko") or p.get("title", "")
    name_en      = p.get("name_en", "")
    brand        = p.get("brand", "")
    category     = p.get("category", "")
    ohouse_url   = p.get("ohouse_url", "#")
    coupang_url  = p.get("coupang_url", "")
    ohouse_price = p.get("ohouse_price", "")
    coupang_price = p.get("coupang_price", "")

    digits = "".join(c for c in (ohouse_price or coupang_price) if c.isdigit())
    price_num = int(digits) if digits else 0

    # CTA buttons
    has_ohouse  = bool(ohouse_url and ohouse_url != "#")
    has_coupang = bool(coupang_url)

    cta_parts = []
    if has_ohouse:
        cta_parts.append(f"""<a class="cta cta-ohouse" href="{ohouse_url}" target="_blank" rel="noopener noreferrer">
            <div class="cta-top">
              <img src="images/todayhouse_nobg.png" alt="오늘의집" class="cta-logo">
              <span class="cta-arrow">↗</span>
            </div>
            <span class="cta-price">{ohouse_price or '—'}</span>
          </a>""")
    if has_coupang:
        cta_parts.append(f"""<a class="cta cta-coupang" href="{coupang_url}" target="_blank" rel="noopener noreferrer">
            <div class="cta-top">
              <img src="images/coupang_nobg.png" alt="쿠팡" class="cta-logo">
              <span class="cta-arrow">↗</span>
            </div>
            <span class="cta-price">{coupang_price or '—'}</span>
          </a>""")

    cta_html = f'<div class="cta-group">{"".join(cta_parts)}</div>'

    brand_html = f'<p class="brand">{brand}</p>' if brand else ""
    name_en_html = ""

    primary_link = ohouse_url if has_ohouse else (coupang_url or "#")

    new_badge = '<img src="images/newsticker_nobg.png" class="new-badge" alt="NEW">' if is_new else ""

    return f"""
    <div class="card" data-category="{category}" data-price="{price_num}" data-order="{order}">
      {brand_html}
      <a class="img-link" href="{primary_link}" target="_blank" rel="noopener noreferrer">
        <div class="img-wrap">
          <img src="{img}" alt="{name_ko}" loading="lazy">
          {new_badge}
        </div>
      </a>
      <div class="info">
        <p class="name-ko">{name_ko}</p>
        {cta_html}
      </div>
    </div>"""


def build_tabs(products: list) -> str:
    counts = {}
    for p in products:
        cat = p.get("category", "")
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    total = len(products)
    tabs = f'<button class="tab active" data-filter="전체">전체 <span class="tab-count">{total}</span></button>'
    for cat, n in counts.items():
        tabs += f'\n    <button class="tab" data-filter="{cat}">{cat} <span class="tab-count">{n}</span></button>'
    return tabs


def generate_html(products: list) -> str:
    total = len(products)
    new_slugs = {p["slug"] for p in products[max(0, total - 6):]}
    cards = "".join(
        build_card(p, order=i, is_new=(p["slug"] in new_slugs))
        for i, p in enumerate(products)
    )
    tabs = build_tabs(products)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{CATALOG_TITLE}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'Segoe UI', 'Apple SD Gothic Neo', Arial, sans-serif;
      background: #f5f4f0;
      color: #1a1a1a;
      padding: 48px 24px 80px;
    }}

    .logo {{
      display: block;
      margin: 0 auto 24px;
      max-height: 120px;
      width: auto;
    }}

    .disclaimers {{
      text-align: center;
      margin-bottom: 32px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}

    .disclaimer {{
      font-size: 0.75rem;
      color: #bbb;
    }}

    .toolbar {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      max-width: 1280px;
      margin: 0 auto 36px;
    }}

    .tabs-wrap {{
      flex: 1;
      min-width: 0;
      position: relative;
    }}

    .tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .tab {{
      border: 1.5px solid #ddd;
      background: #fff;
      border-radius: 999px;
      padding: 8px 20px;
      font-size: 0.88rem;
      font-weight: 500;
      color: #666;
      cursor: pointer;
      transition: all .18s ease;
    }}

    .tab:hover {{ border-color: #aaa; color: #222; }}
    .tab.active {{ background: #1a1a1a; border-color: #1a1a1a; color: #fff; }}

    .tab-count {{ font-size: 0.78rem; font-weight: 400; opacity: 0.6; }}

    .sort-controls {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      flex-shrink: 0;
    }}

    .sort-btn {{
      border: 1.5px solid #ddd;
      background: #fff;
      border-radius: 999px;
      padding: 8px 16px;
      font-size: 0.82rem;
      font-weight: 500;
      color: #666;
      cursor: pointer;
      white-space: nowrap;
      transition: all .18s ease;
    }}

    .sort-btn:hover {{ border-color: #aaa; color: #222; }}
    .sort-btn.active {{ background: #1a1a1a; border-color: #1a1a1a; color: #fff; }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 28px;
      max-width: 1280px;
      margin: 0 auto;
    }}

    .card {{
      background: #fff;
      border-radius: 20px;
      overflow: hidden;
      box-shadow: 0 2px 16px rgba(0,0,0,.06);
      transition: transform .22s ease, box-shadow .22s ease;
      display: flex;
      flex-direction: column;
    }}

    .card:hover {{
      transform: translateY(-6px);
      box-shadow: 0 12px 36px rgba(0,0,0,.12);
    }}

    .card.hidden {{ display: none; }}

    .img-link {{ display: block; text-decoration: none; }}

    /* Warm parchment background so transparent sketch looks great */
    .img-wrap {{
      position: relative;
      width: 100%;
      aspect-ratio: 1 / 1;
      background: #f0ede8;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      padding: 16px;
    }}

    .new-badge {{
      position: absolute;
      top: 0;
      right: 0;
      width: 72px;
      height: auto;
      pointer-events: none;
      z-index: 2;
    }}

    .img-wrap img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
      transition: transform .3s ease;
    }}

    .card:hover .img-wrap img {{ transform: scale(1.04); }}

    .info {{
      padding: 18px 20px 20px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
      justify-content: space-between;
    }}

    .brand {{
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #c05030;
      text-align: center;
      padding: 14px 20px 14px;
    }}

    .name-ko {{
      font-size: 0.95rem;
      font-weight: 600;
      line-height: 1.5;
      color: #1a1a1a;
    }}

    .name-en {{
      font-size: 0.78rem;
      font-weight: 400;
      color: #999;
      font-style: italic;
      margin-bottom: 10px;
    }}

    .cta-group {{
      display: flex;
      gap: 8px;
      margin-top: 10px;
    }}

    .cta {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
      border-radius: 12px;
      padding: 10px 8px;
      text-decoration: none;
      transition: filter .18s ease;
      flex: 1;
    }}

    .cta:hover {{ filter: brightness(0.93); }}

    .cta-ohouse {{
      background: #f0ede8;
      border: 2px solid #B8CDE0;
      color: #1a1a1a;
    }}

    .cta-coupang {{
      background: #f0ede8;
      border: 2px solid #E8C4A8;
      color: #1a1a1a;
    }}

    .cta-top {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}

    .cta-logo {{
      height: 20px;
      width: auto;
      display: block;
    }}

    .cta-arrow {{
      font-size: 0.8rem;
      font-weight: 700;
      color: #333;
    }}

    .cta-price {{
      font-size: 0.82rem;
      font-weight: 700;
    }}

    @media (max-width: 640px) {{
      body {{ padding: 24px 14px 60px; }}
      .logo {{ max-height: 72px; margin-bottom: 16px; }}
      .disclaimers {{ margin-bottom: 16px; }}
      .disclaimer {{ font-size: 0.58rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
      .toolbar {{ flex-direction: column; gap: 10px; margin-bottom: 20px; }}

      .tabs-wrap::after {{
        content: '';
        position: absolute;
        top: 0; right: 0;
        height: 100%; width: 48px;
        background: linear-gradient(to right, transparent, #f5f4f0);
        pointer-events: none;
        transition: opacity .25s;
      }}
      .tabs-wrap.at-end::after {{ opacity: 0; }}
      .tabs {{ flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 4px; scrollbar-width: none; }}
      .tabs::-webkit-scrollbar {{ display: none; }}
      .tab {{ flex-shrink: 0; padding: 7px 14px; font-size: 0.82rem; }}

      .sort-controls {{ flex-direction: row; width: 100%; }}
      .sort-btn {{ flex: 1; text-align: center; padding: 7px 8px; font-size: 0.78rem; }}

      .grid {{ grid-template-columns: repeat(2, 1fr); gap: 10px; }}
      .info {{ padding: 10px 10px 12px; gap: 3px; }}
      .brand {{ font-size: 0.62rem; }}
      .name-ko {{ font-size: 0.78rem; }}
      .name-en {{ font-size: 0.68rem; }}
      .cta-group {{ gap: 6px; margin-top: 8px; }}
      .cta {{ padding: 7px 5px; gap: 3px; border-radius: 10px; }}
      .cta-logo {{ height: 14px; }}
      .cta-arrow {{ font-size: 0.68rem; }}
      .cta-price {{ font-size: 0.70rem; }}
    }}
  </style>
</head>
<body>
  <img src="images/hachizip_nobg.png" alt="hachizip" class="logo">
  <div class="disclaimers">
    <p class="disclaimer">{DISCLAIMER_OHOUSE}</p>
    <p class="disclaimer">{DISCLAIMER_COUPANG}</p>
    <p class="disclaimer">{DISCLAIMER_PRICE}</p>
  </div>
  <div class="toolbar">
    <div class="tabs-wrap">
      <div class="tabs">
        {tabs}
      </div>
    </div>
    <div class="sort-controls">
      <button class="sort-btn" data-sort="newest">최신순 ★</button>
      <button class="sort-btn" data-sort="asc">가격 낮은순 ↑</button>
      <button class="sort-btn" data-sort="desc">가격 높은순 ↓</button>
    </div>
  </div>
  <div class="grid">{cards}
  </div>
  <script>
    const tabs = document.querySelectorAll('.tab');
    const sortBtns = document.querySelectorAll('.sort-btn');
    const grid = document.querySelector('.grid');
    let currentFilter = '전체';
    let currentSort = null;

    function getCards() {{
      return Array.from(grid.querySelectorAll('.card'));
    }}

    function applyFilterAndSort() {{
      const cards = getCards();
      cards.forEach(card => {{
        const match = currentFilter === '전체' || card.dataset.category === currentFilter;
        card.classList.toggle('hidden', !match);
      }});
      if (currentSort) {{
        const visible = cards.filter(c => !c.classList.contains('hidden'));
        const hidden  = cards.filter(c =>  c.classList.contains('hidden'));
        visible.sort((a, b) => {{
          if (currentSort === 'newest') {{
            const oa = parseInt(a.dataset.order) || 0;
            const ob = parseInt(b.dataset.order) || 0;
            return ob - oa;
          }}
          const pa = parseInt(a.dataset.price) || 0;
          const pb = parseInt(b.dataset.price) || 0;
          return currentSort === 'asc' ? pa - pb : pb - pa;
        }});
        [...visible, ...hidden].forEach(c => grid.appendChild(c));
      }}
    }}

    tabs.forEach(tab => {{
      tab.addEventListener('click', () => {{
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentFilter = tab.dataset.filter;
        applyFilterAndSort();
      }});
    }});

    const tabsEl   = document.querySelector('.tabs');
    const tabsWrap = document.querySelector('.tabs-wrap');
    if (tabsEl && tabsWrap) {{
      const updateFade = () => {{
        const atEnd = tabsEl.scrollLeft + tabsEl.clientWidth >= tabsEl.scrollWidth - 4;
        tabsWrap.classList.toggle('at-end', atEnd);
      }};
      tabsEl.addEventListener('scroll', updateFade, {{ passive: true }});
      window.addEventListener('resize', updateFade);
      updateFade();
    }}

    sortBtns.forEach(btn => {{
      btn.addEventListener('click', () => {{
        if (currentSort === btn.dataset.sort) {{
          btn.classList.remove('active');
          currentSort = null;
        }} else {{
          sortBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          currentSort = btn.dataset.sort;
        }}
        applyFilterAndSort();
      }});
    }});
  </script>
</body>
</html>"""


def generate_page(products: list = None):
    if products is None:
        if not PRODUCTS_JSON.exists():
            print("products.json이 없습니다. pipeline.py를 먼저 실행하세요.")
            return
        with open(PRODUCTS_JSON, encoding="utf-8") as f:
            products = json.load(f)

    if not products:
        print("제품이 없습니다.")
        return

    make_sticker_nobg()
    html = generate_html(products)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"index.html 생성 완료 ({len(products)}개 제품)")


def main():
    generate_page()


if __name__ == "__main__":
    main()
