"""
Scraper Carrefour France — https://www.carrefour.fr/promotions

Stratégie : interception des réponses réseau (JSON) + scroll agressif.
Carrefour charge ses produits via des appels API internes (probablement Algolia
ou un backend propre). On intercepte ces réponses pour collecter TOUS les
produits sans limite du DOM (objectif : >10 000 promos).

Fallback DOM si l'API ne répond pas en JSON exploitable :
  - Carte : article.product-list-card-plp-grid-new
  - Nom   : h3.product-card-title__text
  - Prix  : p.product-price__content (entier + décimal concatenés)
  - Image : img.product-card-image-new__content
  - Badge : p.sticker-promo__text
"""
import asyncio
import time
from playwright.async_api import async_playwright
from .base import BaseScraper

# Mots-clés URL qui signalent une réponse API produit
_API_HINTS = ("product", "catalog", "search", "promo", "offer", "item", "algolia")


def _extract_products_from_json(data) -> list[dict]:
    """Cherche une liste de produits dans une réponse JSON quelconque."""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("hits", "results", "products", "items", "data", "offers"):
        val = data.get(key)
        if isinstance(val, list) and val:
            return _extract_products_from_json(val) if key == "data" else val
        if isinstance(val, dict):
            nested = _extract_products_from_json(val)
            if nested:
                return nested
    return []


def _extract_promos_from_item(item: dict) -> list[dict]:
    """
    Un item API Carrefour est un wrapper (type 'sponsored_products' ou autre)
    qui contient une liste 'products'. Chaque produit a ses données dans 'attributes'.
    """
    results = []
    nested = item.get("products") or []
    # Si pas de nested, tenter l'item lui-même comme produit direct
    candidates = nested if nested else [item]

    for p in candidates:
        if not isinstance(p, dict):
            continue
        attrs = p.get("attributes") or p

        name = attrs.get("title") or attrs.get("shortTitle") or attrs.get("name")
        if not name:
            continue

        # Image : paths contient des URLs avec "FORMAT" à remplacer
        img = None
        imgs_obj = attrs.get("images") or {}
        if isinstance(imgs_obj, dict):
            paths = imgs_obj.get("paths") or []
            if paths:
                img = str(paths[0]).replace("FORMAT", "540x540")

        # Prix + promo depuis les offres imbriquées
        promo_price = None
        orig_price  = None
        disc_pct    = None
        badge       = None

        offers_map = attrs.get("offers") or {}
        if isinstance(offers_map, dict):
            for ean_offers in offers_map.values():
                if not isinstance(ean_offers, dict):
                    continue
                for offer_obj in ean_offers.values():
                    if not isinstance(offer_obj, dict):
                        continue
                    oattrs = offer_obj.get("attributes") or offer_obj
                    price_info = oattrs.get("price") or {}
                    promo_price = price_info.get("price")

                    promo_info = oattrs.get("promotion") or {}
                    badge = promo_info.get("label")
                    # Extraire le % depuis le libellé ("30% d'économies" → 30)
                    if badge:
                        import re as _re
                        m = _re.search(r"(\d+)\s*%", badge)
                        if m:
                            disc_pct = float(m.group(1))
                    # Prix barré éventuel
                    msg = promo_info.get("messageArgs") or {}
                    raw_orig = msg.get("initialPrice")
                    # initialPrice = prix total pour N articles, on ramène à l'unité
                    qty = msg.get("quantity") or 1
                    if raw_orig and qty:
                        orig_price = round(float(raw_orig) / int(qty), 2)
                    break
                break

        # Catégorie depuis le slug
        slug = attrs.get("slug") or ""
        cat = CarrefourScraper._cat_from_href(slug)

        results.append({
            "name":  str(name).strip(),
            "promo": promo_price,
            "orig":  orig_price,
            "disc":  disc_pct,
            "img":   img,
            "cat":   cat,
            "badge": badge,
        })
    return results


class CarrefourScraper(BaseScraper):
    STORE_NAME = "carrefour"
    URL = "https://www.carrefour.fr/promotions"

    async def scrape(self):
        promos = []
        api_products: list[dict] = []

        async with async_playwright() as p:
            browser, page = await self.new_browser_page(p)
            try:
                # ── Interception réseau ───────────────────────────────────────
                async def on_response(response):
                    url = response.url
                    if "carrefour.fr" not in url:
                        return
                    if not any(h in url.lower() for h in _API_HINTS):
                        return
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    try:
                        data = await response.json()
                    except Exception:
                        return
                    products = _extract_products_from_json(data)
                    if products:
                        api_products.extend(products)
                        print(f"[CARREFOUR API] +{len(products)} → {len(api_products)} total")

                page.on("response", on_response)

                await page.goto(self.URL, wait_until="domcontentloaded", timeout=30_000)

                # Cookies Carrefour (Didomi)
                for sel in [
                    "#didomi-notice-agree-button",
                    "button:has-text('Tout accepter')",
                    "button:has-text('Accepter')",
                ]:
                    try:
                        await page.click(sel, timeout=3_000)
                        break
                    except Exception:
                        pass

                try:
                    await page.wait_for_selector(
                        "article.product-list-card-plp-grid-new", timeout=12_000
                    )
                except Exception:
                    pass

                # Scroll + clic "Charger plus" pour déclencher tous les appels API
                prev_api = 0
                no_new_streak = 0
                _t0 = time.monotonic()
                for _ in range(200):
                    if self.is_cancelled() or (time.monotonic() - _t0) > 240:
                        print(f"[CARREFOUR] Arrêt — {len(api_products)} produits collectés")
                        break
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(500)

                    # Attendre que le bouton "Charger plus" soit présent, puis cliquer
                    btn_sel = "button:has-text('Charger plus'), button:has-text('Voir plus'), button:has-text('Afficher plus')"
                    try:
                        await page.wait_for_selector(btn_sel, timeout=1_500)
                        await page.locator(btn_sel).first.click(timeout=2_000)
                        await page.wait_for_timeout(1_200)
                    except Exception:
                        pass

                    api_now = len(api_products)
                    print(f"[CARREFOUR] API:{api_now}…")
                    if api_now == prev_api:
                        no_new_streak += 1
                        if no_new_streak >= 10:
                            break
                    else:
                        no_new_streak = 0
                    prev_api = api_now

                # ── Mapping selon la source ───────────────────────────────────
                if api_products:
                    seen: set[str] = set()
                    for raw in api_products:
                        for mapped in _extract_promos_from_item(raw):
                            if mapped["name"] in seen:
                                continue
                            seen.add(mapped["name"])
                            promos.append(self.make_promo(
                                name=mapped["name"],
                                category=mapped["cat"],
                                promo_price=mapped["promo"],
                                original_price=mapped["orig"],
                                discount_percent=mapped["disc"],
                                image_url=mapped["img"],
                                description=mapped["badge"],
                            ))
                else:
                    # Fallback DOM
                    print("[CARREFOUR] Fallback DOM")
                    items = await page.evaluate("""() => {
                        return [...document.querySelectorAll('article.product-list-card-plp-grid-new')]
                            .map(card => {
                                const nameEl   = card.querySelector('h3.product-card-title__text');
                                const imgEl    = card.querySelector('img.product-card-image-new__content');
                                const badgeEl  = card.querySelector('p.sticker-promo__text');
                                const priceEls = [...card.querySelectorAll('p.product-price__content')];
                                const link     = card.querySelector('a[href]');
                                return {
                                    name:     nameEl  ? nameEl.innerText.trim()                    : null,
                                    img:      imgEl   ? imgEl.src                                  : null,
                                    badge:    badgeEl ? badgeEl.innerText.trim()                   : null,
                                    rawPrice: priceEls.map(e => e.innerText.trim()).join(''),
                                    href:     link    ? link.getAttribute('href')                  : '',
                                };
                            }).filter(i => i.name);
                    }""")
                    for item in items:
                        promos.append(self.make_promo(
                            name=item["name"],
                            category=self._cat_from_href(item.get("href", "")),
                            promo_price=self.parse_price(item["rawPrice"]),
                            discount_percent=self.parse_discount(item["badge"]),
                            image_url=item["img"],
                            description=item["badge"],
                        ))

            finally:
                try:
                    proc = getattr(browser, "process", None)
                    if proc and proc.returncode is None:
                        proc.kill()
                except Exception:
                    pass

        return promos

    @staticmethod
    def _cat_from_href(href: str) -> str:
        href = href.lower()
        mapping = {
            "epicerie": "Épicerie", "boisson": "Boissons", "surgel": "Surgelés",
            "frais": "Frais", "viande": "Boucherie", "charcuterie": "Charcuterie",
            "poisson": "Poissonnerie", "fromage": "Fromage", "fruit": "Fruits & Légumes",
            "hygien": "Hygiène", "entretien": "Entretien", "bebe": "Bébé",
            "animal": "Animaux", "electromenager": "Électronique",
            "informatique": "Électronique", "sport": "Sport", "jardin": "Jardin",
            "bricolage": "Bricolage", "textile": "Textile", "vetement": "Textile",
            "maison": "Maison",
        }
        for kw, cat in mapping.items():
            if kw in href:
                return cat
        return "Autre"
