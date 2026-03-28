"""
Scraper Lidl France — https://www.lidl.fr/q/query/promotions

Stratégie : interception des réponses réseau de l'API Lidl.
Le site utilise le virtual scrolling (les anciens articles disparaissent du DOM),
donc on ne peut pas extraire depuis le DOM après plusieurs scrolls.
On intercepte les appels JSON de l'API de recherche pour récupérer tous les
produits dès qu'ils sont chargés, sans passer par le DOM.

Sélecteurs DOM (fallback si l'API change) :
  - Carte     : div.odsc-tile__inner
  - Prix promo: div.ods-price__value
  - Prix barré: div.ods-price__stroke-price
  - Remise    : span.ods-price__box-content-text-el
"""
import time
from playwright.async_api import async_playwright
from .base import BaseScraper


class LidlScraper(BaseScraper):
    STORE_NAME = "lidl"
    URL = "https://www.lidl.fr/q/query/promotions"

    async def scrape(self):
        promos = []
        api_products: list[dict] = []   # collectés via interception réseau

        async with async_playwright() as p:
            browser, page = await self.new_browser_page(p)
            try:
                # ── Interception réseau ───────────────────────────────────────
                async def on_response(response):
                    url = response.url
                    if "lidl.fr" not in url:
                        return
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    try:
                        data = await response.json()
                    except Exception:
                        return

                    # L'API Lidl renvoie les produits dans différentes clés
                    if not isinstance(data, dict):
                        return
                    products = (
                        data.get("results")
                        or data.get("products")
                        or data.get("hits")
                        or data.get("items")
                        or (data.get("data") or {}).get("results")
                    )
                    if products and isinstance(products, list):
                        api_products.extend(products)
                        print(f"[LIDL API] +{len(products)} → {len(api_products)} total")

                page.on("response", on_response)

                await page.goto(self.URL, wait_until="domcontentloaded", timeout=30_000)

                # Cookies
                for sel in [
                    "#onetrust-accept-btn-handler",
                    "button:has-text('Accepter tout')",
                    "button:has-text('Accepter')",
                ]:
                    try:
                        await page.click(sel, timeout=3_000)
                        break
                    except Exception:
                        pass

                # Attendre le premier produit
                try:
                    await page.wait_for_selector("div.odsc-tile__inner", timeout=12_000)
                except Exception:
                    pass

                # Scroll pour déclencher tous les appels API
                prev_api = 0
                no_new_streak = 0
                _t0 = time.monotonic()
                for _ in range(150):
                    if self.is_cancelled() or (time.monotonic() - _t0) > 180:
                        break
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1_000)

                    now = len(api_products)
                    if now == prev_api:
                        no_new_streak += 1
                        if no_new_streak >= 10:
                            break
                    else:
                        no_new_streak = 0
                        prev_api = now

                print(f"[LIDL] {len(api_products)} produits via API")

                # ── Mapping des produits API → Promotion ──────────────────────
                if api_products:
                    seen_names: set[str] = set()
                    for product in api_products:
                        name = (
                            product.get("fullTitle")
                            or product.get("title")
                            or product.get("name")
                            or product.get("gridboxTitle")
                        )
                        if not name or name in seen_names:
                            continue
                        seen_names.add(name)

                        price_info = product.get("price") or {}
                        promo  = price_info.get("price") or price_info.get("newPrice")
                        orig   = price_info.get("regularPrice") or price_info.get("rrp")
                        disc   = price_info.get("discount") or price_info.get("percentage")

                        images = product.get("imageList") or product.get("image") or []
                        img = None
                        if isinstance(images, list) and images:
                            img = images[0].get("url") or images[0] if isinstance(images[0], str) else None
                        elif isinstance(images, str):
                            img = images

                        # Catégorie
                        cats = product.get("category") or product.get("categorySecondaryPath") or []
                        cat = "Autre"
                        if isinstance(cats, list) and cats:
                            cat = cats[-1] if isinstance(cats[-1], str) else cats[-1].get("name", "Autre")
                        elif isinstance(cats, str):
                            cat = cats

                        promos.append(self.make_promo(
                            name=str(name),
                            category=str(cat),
                            original_price=float(orig) if orig else None,
                            promo_price=float(promo) if promo else None,
                            discount_percent=float(str(disc).replace("%", "").replace("-", "")) if disc else None,
                            image_url=img,
                        ))

                else:
                    # ── Fallback DOM (si l'API n'a rien renvoyé) ─────────────
                    print("[LIDL] Fallback DOM (API vide)")
                    EXTRACT_JS = """() => {
                        return [...document.querySelectorAll('div.odsc-tile__inner')].map(card => {
                            const titleEl = card.querySelector('div.product-grid-box__title');
                            const brandEl = card.querySelector('div.product-grid-box__brand');
                            const imgEl   = card.querySelector('img.odsc-image-gallery__image');
                            const priceEl = card.querySelector('div.ods-price__value');
                            const origEl  = card.querySelector('div.ods-price__stroke-price');
                            const discEl  = card.querySelector('span.ods-price__box-content-text-el');
                            const title   = titleEl ? titleEl.innerText.trim() : null;
                            const brand   = brandEl ? brandEl.innerText.trim() : '';
                            return {
                                name:     brand ? brand + ' ' + title : title,
                                img:      imgEl   ? imgEl.src                : null,
                                price:    priceEl ? priceEl.innerText.trim() : null,
                                orig:     origEl  ? origEl.innerText.trim()  : null,
                                discount: discEl  ? discEl.innerText.trim()  : null,
                            };
                        }).filter(i => i.name);
                    }"""
                    items = await page.evaluate(EXTRACT_JS)
                    for item in items:
                        promos.append(self.make_promo(
                            name=item["name"],
                            original_price=self.parse_price(item["orig"]),
                            promo_price=self.parse_price(item["price"]),
                            discount_percent=self.parse_discount(item["discount"]),
                            image_url=item["img"],
                        ))

            finally:
                try:
                    proc = getattr(browser, "process", None)
                    if proc and proc.returncode is None:
                        proc.kill()
                except Exception:
                    pass

        return promos
