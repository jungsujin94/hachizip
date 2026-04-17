# productspage

## 개요
가구/홈데코 제품 URL(오늘의집/쿠팡)을 받아 수채화 스케치 이미지를 생성하고,
GitHub Pages용 제품 카탈로그 index.html을 자동으로 빌드합니다.

## 핵심 파일
- `pipeline.py` — 메인 진입점
- `scraper.js` — Playwright 스크래퍼 (ohou.se / coupang.com)
- `renderer.py` — 수채화 스케치 + 배경 제거 엔진
- `extractor.py` — Claude API: slug, 정제된 제품명, 카테고리 추출
- `page.py` — index.html 생성기

## API 키
`.env` 파일에 `ANTHROPIC_API_KEY` 필요 (`.env.example` 참고). 절대 커밋 금지.

## 실행
```bash
# 오늘의집 URL 하나만
python pipeline.py https://www.ohou.se/products/XXXXX

# 쿠팡 URL 하나만
python pipeline.py https://www.coupang.com/vp/products/XXXXX

# 두 URL 모두 (가격 비교 표시)
python pipeline.py --ohouse URL --coupang URL
```

## 출력
- `products/{slug}.png` — 수채화 스케치 이미지 (투명 배경)
- `products.json` — 누적 제품 데이터
- `index.html` — GitHub Pages 배포용 카탈로그

## 카드 구조
각 제품 카드: 스케치 이미지(크게, 중앙) + 브랜드 + 한국어 제품명 + 영문명 + 구매 링크(가격 포함)

## 스킬 호출
Claude Code에서 `/productspage [URL]` 입력

## 설치 (최초 1회)
```bash
pip install -r requirements.txt
npm install
npx playwright install chromium
```
