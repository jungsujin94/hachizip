/**
 * scraper.js — Playwright 기반 가구 제품 페이지 스크래퍼
 * 사용: node scraper.js [URL]
 * 출력: JSON to stdout
 */

const { chromium } = require('playwright-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
chromium.use(StealthPlugin());

const url = process.argv[2];
if (!url) {
  process.stderr.write(JSON.stringify({ error: 'URL이 필요합니다. 사용법: node scraper.js [URL]' }) + '\n');
  process.exit(1);
}

function detectSite(url) {
  if (url.includes('ohou.se')) return 'ohou';
  if (url.includes('coupang.com')) return 'coupang';
  return 'unknown';
}

function randomDelay(min = 1000, max = 3000) {
  return new Promise(resolve => setTimeout(resolve, Math.floor(Math.random() * (max - min) + min)));
}

async function scrapeOhou(page) {
  try {
    await page.waitForSelector('h1, [class*="GoodsName"], [class*="goods-name"], [class*="ProductName"], [class*="product-name"]', { timeout: 20000 });
  } catch (e) {}
  // 전체 페이지를 단계적으로 스크롤해 레이지 로딩 이미지 모두 트리거
  await page.evaluate(async () => {
    await new Promise(resolve => {
      const totalHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
      const step = 400;
      let current = 0;
      const timer = setInterval(() => {
        window.scrollTo(0, current);
        current += step;
        if (current >= totalHeight) {
          clearInterval(timer);
          resolve();
        }
      }, 150);
    });
  });
  await randomDelay(1200, 1800);
  await page.evaluate(() => window.scrollTo(0, 0));
  await randomDelay(600, 1000);

  // 컬러 옵션으로 모든 변형 이미지 수집 (select 드롭다운 + 버튼 스와치 모두 지원)
  const variantImageUrls = new Set();
  const galleryImgSelectors = '[class*="GoodsImageGallery"] img, [class*="ImageSwiper"] img, [class*="MainImage"] img, [class*="GoodsSwiper"] img, [class*="pdp-image"] img';
  try {
    // 1) <select> 드롭다운 방식 (오늘의집 일반)
    const colorSelects = await page.$$('select');
    for (const sel of colorSelects.slice(0, 2)) {
      const optCount = await sel.evaluate(s => s.options.length);
      for (let i = 1; i < Math.min(optCount, 5); i++) {
        try {
          await sel.selectOption({ index: i });
          await page.waitForTimeout(500);
          const urls = await page.$$eval(galleryImgSelectors,
            imgs => imgs.map(img => img.src || '').filter(s => s.startsWith('http') && s.includes('uploads'))
          );
          urls.forEach(u => variantImageUrls.add(u.split('?')[0]));
        } catch(e) {}
      }
      if (variantImageUrls.size > 0) break; // 첫 select에서 수집되면 중단
    }

    // 2) 버튼·칩 방식 fallback
    if (variantImageUrls.size === 0) {
      const swatchSelectors = [
        '[class*="ColorChip"]', '[class*="colorChip"]',
        '[class*="ColorOption"] button', '[class*="OptionColor"] button',
        '[class*="GoodsOption"] [class*="Chip"]', '[class*="option-chip"]',
      ];
      let swatches = [];
      for (const ss of swatchSelectors) {
        swatches = await page.$$(ss);
        if (swatches.length > 0) break;
      }
      for (const swatch of swatches.slice(0, 6)) {
        try {
          await swatch.click();
          await page.waitForTimeout(500);
          const urls = await page.$$eval(galleryImgSelectors,
            imgs => imgs.map(img => img.src || '').filter(s => s.startsWith('http') && s.includes('uploads'))
          );
          urls.forEach(u => variantImageUrls.add(u.split('?')[0]));
        } catch(e) {}
      }
    }
  } catch(e) {}

  return await page.evaluate((extraUrls) => {
    const getText = (selectors) => {
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.textContent.trim()) return el.textContent.trim();
      }
      return '';
    };

    const getAllText = (selectors) => {
      const results = [];
      for (const sel of selectors) {
        document.querySelectorAll(sel).forEach(el => {
          const t = el.textContent.trim();
          if (t && t.length > 3) results.push(t);
        });
      }
      return results;
    };

    // ── 제품명
    // 0순위: og:title 메타태그 (단독 페이지의 실제 제품명, 관련상품 오염 없음)
    const ogTitle = document.querySelector('meta[property="og:title"]')
      ?.getAttribute('content')?.trim() || '';

    // 1순위: 페이지 구조 선택자 (main 안의 h1/product-name 등)
    // main 요소 내부로 범위 제한해 관련상품 섹션 오염 방지
    const mainEl = document.querySelector('main') || document;
    const getTextIn = (root, selectors) => {
      for (const sel of selectors) {
        const el = root.querySelector(sel);
        if (el && el.textContent.trim()) return el.textContent.trim();
      }
      return '';
    };
    const domName = getTextIn(mainEl, [
      '[class*="GoodsName"]', '[class*="goods-name"]',
      '[class*="pdp-product-name"]', '[class*="itemName"]',
      '.product_name', '.goods_name', 'h1.title', 'h1'
    ]);

    // 2순위: title 태그 파싱 ("> 제품명 |" 패턴)
    const titleRaw = document.title;
    const titleMatch = titleRaw.match(/>\s*(.+?)\s*\|/);
    const titleName = titleMatch ? titleMatch[1].trim() : titleRaw.replace(/\s*[|].*$/, '').trim();

    const name = ogTitle || domName || titleName;

    // ── 가격: 특정 선택자 우선, 없으면 최고금액 fallback
    let price = '';

    // 1순위: JSON-LD 구조화 데이터
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const d = JSON.parse(script.textContent);
        const offerPrice = d?.offers?.price || d?.price;
        if (offerPrice) {
          const n = parseFloat(String(offerPrice).replace(/,/g, ''));
          if (n >= 5000) { price = n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '원'; break; }
        }
      } catch(e) {}
    }

    // 2순위: 가격 전용 선택자
    if (!price) {
      const priceSelectors = [
        '[class*="GoodsPrice"][class*="selling"]',
        '[class*="SellingPrice"]', '[class*="sellingPrice"]',
        '[class*="SalePrice"]', '[class*="salePrice"]',
        '[class*="FinalPrice"]', '[class*="finalPrice"]',
        '[class*="GoodsDetailPrice"]', '[class*="goods-detail-price"]',
        '[class*="PriceValue"]', '[class*="price-value"]',
        '[class*="price"][class*="final"]',
        'meta[property="product:price:amount"]',
        'meta[name="product:price:amount"]'
      ];
      for (const sel of priceSelectors) {
        const el = document.querySelector(sel);
        if (el) {
          const raw = el.tagName === 'META' ? el.getAttribute('content') : el.textContent;
          const m = raw && raw.match(/([\d,]{4,})/);
          if (m) {
            const n = parseInt(m[1].replace(/,/g, ''));
            if (n >= 5000) { price = m[1] + '원'; break; }
          }
        }
      }
    }

    // 3순위: 페이지 텍스트에서 최고금액 (배송비/쿠폰 노이즈 방지)
    if (!price) {
      const bodyText = document.body.innerText;
      const priceMatches = [...bodyText.matchAll(/([\d,]{4,})\s*원/g)]
        .map(m => ({ text: m[1].replace(/,/g, ''), raw: m[1] + '원' }))
        .map(p => ({ ...p, num: parseInt(p.text) }))
        .filter(p => p.num >= 10000 && p.num <= 9999999);
      if (priceMatches.length) {
        // 배송비/쿠폰(낮은 가격)보다 실제 판매가(높은 가격)를 우선: 최고값 사용
        priceMatches.sort((a, b) => b.num - a.num);
        price = priceMatches[0].raw;
      }
    }

    // 할인율
    const bodyText = document.body.innerText;
    const discountMatch = bodyText.match(/(\d+)\s*%\s*(?:할인|OFF|off)/);
    const discount = discountMatch ? discountMatch[1] + '%' : '';

    // ── 설명
    const description = getText([
      '[class*="Description"]', '[class*="description"]',
      '[class*="GoodsDetail"]', '[class*="goods-detail"]',
      '[class*="ProductDetail"]', '[class*="product-detail"]',
      '[class*="content-body"]', '[class*="detailContent"]'
    ]);

    // ── 스펙/피처
    const features = getAllText([
      '[class*="Spec"] li', '[class*="spec"] li',
      '[class*="Feature"] li', '[class*="feature"] li',
      '[class*="Info"] li', '[class*="detail"] li',
      'table tr', '[class*="attribute"]'
    ]);

    // ── 이미지: 제품 갤러리 컨테이너 우선 → fallback 전체 스캔
    const seenBase = new Set();
    const isValidProductImg = (img) => {
      const src = img.src || img.dataset.src || img.dataset.lazySrc || img.dataset.original || img.getAttribute('data-lazy') || '';
      if (!src.startsWith('http')) return null;
      if (!src.includes('ohousecdn.com') && !src.includes('ohou.se')) return null;
      if (src.includes('.svg') || src.includes('icon') || src.includes('logo')
          || src.includes('banner') || src.includes('percent')
          || src.includes('cards/snapshots') || src.includes('/cards/')
          || src.includes('/community/')
          || src.includes('/seller/') || src.includes('notice_images')
          || src.includes('video-service')
          || src.includes('/admins/')) return null;
      // prs.ohousecdn.com/apne2/any/v1-XXXXX (uploads/ 없음) → 관련상품/리뷰 이미지
      if (src.includes('ohousecdn.com') && src.includes('/any/v1-') && !src.includes('/uploads/')) return null;
      // CDN w= 파라미터가 256 이하면 관련상품 썸네일 → 제외
      const wMatch = src.match(/[?&]w=(\d+)/);
      if (wMatch && parseInt(wMatch[1]) <= 256) return null;
      const goodSize = img.naturalWidth >= 200 || img.naturalHeight >= 200
                    || (!img.getAttribute('width') && src.includes('uploads'));
      if (!goodSize) return null;
      const baseUrl = src.split('?')[0];
      if (seenBase.has(baseUrl)) return null;
      seenBase.add(baseUrl);
      return src;
    };

    // 1순위: 제품 이미지 갤러리 컨테이너 (관련상품 오염 없음)
    const gallerySelectors = [
      '[class*="GoodsImageGallery"]', '[class*="goods-image-gallery"]',
      '[class*="ProductImageGallery"]', '[class*="ProductImages"]',
      '[class*="ImageSwiper"]', '[class*="image-swiper"]',
      '[class*="GoodsSwiper"]', '[class*="GoodsImageSlider"]',
      '[class*="MainImage"]', '[class*="main-image"]',
      '[class*="GoodsThumbs"]', '[class*="GoodsThumb"]',
      '[class*="pdp-image"]', '[class*="PdpImage"]',
    ];
    const productImgUrls = [];
    for (const sel of gallerySelectors) {
      const container = document.querySelector(sel);
      if (!container) continue;
      container.querySelectorAll('img').forEach(img => {
        const src = isValidProductImg(img);
        if (src && !productImgUrls.includes(src)) productImgUrls.push(src);
      });
      if (productImgUrls.length >= 3) break; // 충분히 찾으면 중단
    }

    // 2순위: 전체 페이지 스캔 (갤러리에서 못 찾은 경우)
    if (productImgUrls.length < 3) {
      const detailImgUrls = [];
      document.querySelectorAll('img').forEach(img => {
        const src = isValidProductImg(img);
        if (!src) return;
        const isDetailShot = src.includes('/uploads/admin') || src.includes('/v2-development/');
        if (isDetailShot) {
          detailImgUrls.push(src);
        } else {
          productImgUrls.push(src);
        }
      });
      productImgUrls.push(...detailImgUrls);
    }

    // 3순위: 갤러리 썸네일 스트립 (w=72 소형 이미지 → 베이스 URL 추출해 풀해상도로 추가)
    // 컬러 변형 이미지가 썸네일로만 존재하는 경우를 커버
    // PNG는 인포그래픽/설명 이미지일 가능성이 높으므로 제외
    const thumbAdded = new Set(productImgUrls.map(u => u.split('?')[0]));
    document.querySelectorAll('img').forEach(img => {
      const src = img.src || '';
      if (!src.includes('ohousecdn.com') && !src.includes('ohou.se')) return;
      if (!src.includes('uploads/productions')) return;
      if (src.includes('/admins/') || src.includes('/community/') || src.includes('/seller/')) return;
      if (src.includes('.png') || src.includes('.svg')) return; // 인포그래픽/아이콘 제외
      const wMatch = src.match(/[?&]w=(\d+)/);
      if (!wMatch || parseInt(wMatch[1]) > 256) return; // 이 블록은 소형 썸네일만 처리
      const base = src.split('?')[0];
      if (!thumbAdded.has(base)) {
        thumbAdded.add(base);
        productImgUrls.push(base); // 쿼리 파라미터 없는 풀해상도 URL
      }
    });

    // 컬러 변형 이미지 병합 (extraUrls: base URL 목록)
    if (extraUrls && extraUrls.length > 0) {
      const seenVariant = new Set(productImgUrls.map(u => u.split('?')[0]));
      for (const base of extraUrls) {
        if (!seenVariant.has(base)) {
          seenVariant.add(base);
          productImgUrls.push(base);
        }
      }
    }

    const imageUrls = productImgUrls.slice(0, 8);

    // ── 리뷰/평점
    const rating = getText([
      '[class*="Rating"]', '[class*="rating"]',
      '[class*="Score"]', '[class*="score"]'
    ]);

    // 브랜드: /brands/ 링크가 가장 신뢰도 높음 (관련상품 오염 없음)
    let brand = '';
    const brandLink = document.querySelector('a[href*="/brands/"]');
    if (brandLink) {
      brand = brandLink.textContent.trim().replace(/브랜드$/, '').trim();
    }
    if (!brand) {
      brand = getTextIn(mainEl, [
        '[class*="Brand"]', '[class*="brand"]',
        '[class*="Store"]', '[class*="store"]',
        '[class*="Seller"]', '[class*="seller"]'
      ]);
    }

    return {
      name,
      price,
      discount,
      description: description.slice(0, 1000),
      features: features.slice(0, 15),
      imageUrls: imageUrls.slice(0, 8),
      rating,
      brand,
      url: window.location.href
    };
  }, [...variantImageUrls]);
}

async function scrapeCoupang(page) {
  await page.waitForSelector('#prod-title, .prod-buy-header__title, h1', { timeout: 20000 });
  await randomDelay(1000, 2000);

  return await page.evaluate(() => {
    const getText = (selectors) => {
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.textContent.trim()) return el.textContent.trim();
      }
      return '';
    };

    const name = getText([
      '#prod-title',
      '.prod-buy-header__title',
      'h1.prod-buy-header__title',
      'h1'
    ]);

    const price = getText([
      '.prod-price-cost',
      '.total-price strong',
      '[class*="price-cost"]',
      '.price'
    ]);

    const description = getText([
      '#btf-tab-contents',
      '.product-description',
      '.tab-contents__content'
    ]);

    const features = [];
    document.querySelectorAll('.prod-attr-item, .prod-spec li, [class*="attribute"] li').forEach(el => {
      const text = el.textContent.trim().replace(/\s+/g, ' ');
      if (text && text.length > 3) features.push(text);
    });

    // 상품 상세 이미지 가져오기
    const imageUrls = [];
    document.querySelectorAll('.prod-image__detail img, .detail-item-imgs img, .thumb-item img').forEach(img => {
      const src = img.src || img.dataset.src;
      if (src && src.startsWith('http') && !imageUrls.includes(src)) {
        imageUrls.push(src);
      }
    });
    // 대표 이미지도 포함
    document.querySelectorAll('.prod-buy-header img, .prod-image img').forEach(img => {
      const src = img.src || img.dataset.src;
      if (src && src.startsWith('http') && !imageUrls.includes(src)) {
        imageUrls.unshift(src);
      }
    });

    const rating = getText(['.rating-star-num', '[class*="rating"]', '.score-star']);

    const brand = getText([
      '.prod-brand',
      '[class*="brand-name"]',
      '.vendorItemsTitle'
    ]);

    return {
      name,
      price,
      description: description.slice(0, 1000),
      features: features.slice(0, 15),
      imageUrls: imageUrls.slice(0, 5),
      rating,
      brand,
      url: window.location.href
    };
  });
}

(async () => {
  const site = detectSite(url);
  if (site === 'unknown') {
    process.stderr.write(JSON.stringify({ error: '지원하지 않는 사이트입니다. ohou.se 또는 coupang.com URL을 사용하세요.' }) + '\n');
    process.exit(1);
  }

  const browser = await chromium.launch({
    headless: true,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--lang=ko-KR'
    ]
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    locale: 'ko-KR',
    viewport: { width: 1366 + Math.floor(Math.random() * 200), height: 768 + Math.floor(Math.random() * 100) },
    extraHTTPHeaders: {
      'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
  });

  const page = await context.newPage();

  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await randomDelay(1500, 3000);

    let result;
    if (site === 'ohou') {
      result = await scrapeOhou(page);
    } else {
      result = await scrapeCoupang(page);
    }

    result.site = site;

    // 가격 형식 정규화: "202400원" → "202,400원"
    if (result.price) {
      const num = parseInt(result.price.replace(/[^\d]/g, ''), 10);
      if (!isNaN(num)) {
        result.price = num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '원';
      }
    }

    if (!result.name) {
      // 쿠팡 모바일 버전 폴백
      if (site === 'coupang') {
        const mobileUrl = url.replace('www.coupang.com', 'm.coupang.com');
        process.stderr.write(`[scraper] 데스크톱 버전 스크래핑 실패, 모바일 버전 시도: ${mobileUrl}\n`);
        await page.goto(mobileUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await randomDelay(1500, 2500);
        result = await scrapeCoupang(page);
        result.site = site;
      }
    }

    if (!result.name) {
      process.stderr.write(JSON.stringify({ error: '제품 정보를 찾을 수 없습니다. 페이지 구조가 변경되었거나 접근이 차단되었을 수 있습니다.' }) + '\n');
      process.exit(1);
    }

    process.stdout.write(JSON.stringify(result, null, 2));
  } catch (err) {
    process.stderr.write(JSON.stringify({ error: err.message }) + '\n');
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
