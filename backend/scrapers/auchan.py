"""
Scraper Auchan France — https://www.auchan.fr/boutique/promos

Sélecteurs confirmés (mars 2026) :
  - Carte     : article[itemtype='http://schema.org/Product']
  - Nom       : p[itemprop='name description']
  - Image     : img[src*='cdn.auchan']
  - Prix      : Chargés après sélection du magasin Saint-Priest (69800)

Flux : sélection magasin → navigation promos → scraping DOM
"""
import asyncio
import time
from playwright.async_api import async_playwright
from .base import BaseScraper

STORE_SEARCH = "Saint-Priest"
STORE_ZIP    = "69800"


class AuchanScraper(BaseScraper):
    STORE_NAME = "auchan"
    URL_PROMOS = "https://www.auchan.fr/boutique/promos"

    async def scrape(self):
        promos = []
        api_products: list[dict] = []

        async with async_playwright() as p:
            browser, page = await self.new_browser_page(p)
            try:
                # ── Interception réseau ───────────────────────────────────────
                async def on_response(response):
                    url = response.url
                    if "auchan.fr" not in url:
                        return
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    try:
                        data = await response.json()
                    except Exception:
                        return
                    if not isinstance(data, dict):
                        return
                    products = (
                        data.get("hits")
                        or data.get("results")
                        or data.get("products")
                        or data.get("items")
                        or (data.get("data") or {}).get("hits")
                        or (data.get("data") or {}).get("products")
                    )
                    if products and isinstance(products, list):
                        api_products.extend(products)
                        print(f"[AUCHAN API] +{len(products)} → {len(api_products)} total")

                page.on("response", on_response)

                # ── 1. Page d'accueil + cookies ──────────────────────────────
                await page.goto(
                    "https://www.auchan.fr", wait_until="domcontentloaded", timeout=30_000
                )
                for sel in [
                    "#onetrust-accept-btn-handler",
                    "button:has-text('Tout accepter')",
                    "button:has-text('Accepter')",
                ]:
                    try:
                        await page.click(sel, timeout=3_000)
                        break
                    except Exception:
                        pass
                await page.wait_for_timeout(2_000)

                # ── 2. Ouvrir la modale de sélection de magasin ─────────────
                # On évite "Choisir" seul car ça peut matcher les boutons
                # dans les résultats. On cherche l'élément header/nav qui
                # ouvre la modale "Choisir un drive ou la livraison".
                store_opened = False
                for sel in [
                    "button:has-text('Choisir votre')",
                    "button:has-text('Choisir un drive')",
                    "button:has-text('En drive')",
                    "button:has-text('Votre magasin')",
                    # fallback : le 1er "Choisir" sur la page d'accueil
                    # est normalement le bouton d'ouverture de la modale
                    "button:has-text('Choisir')",
                ]:
                    try:
                        await page.click(sel, timeout=3_000)
                        store_opened = True
                        break
                    except Exception:
                        pass

                if store_opened:
                    # Attendre le champ de saisie
                    try:
                        await page.wait_for_selector(
                            "input[placeholder*='ville'], input[placeholder*='Code'], input[placeholder*='postal']",
                            timeout=5_000
                        )
                    except Exception:
                        await page.wait_for_timeout(2_000)

                    # Typer caractère par caractère pour déclencher l'autocomplétion
                    for inp in [
                        "input[placeholder*='ville']",
                        "input[placeholder*='Code']",
                        "input[placeholder*='postal']",
                    ]:
                        try:
                            await page.click(inp, timeout=2_000)
                            await page.type(inp, STORE_ZIP, delay=80)
                            await page.wait_for_timeout(2_000)
                            break
                        except Exception:
                            pass

                    # Cliquer sur la 1re suggestion d'autocomplétion
                    clicked_sug = False
                    for sug_sel in [
                        "li[class*='suggest']",
                        "[role='option']",
                        "[class*='autocomplete'] li",
                        "[class*='suggestion']",
                        f"li:has-text('{STORE_ZIP}')",
                        f"li:has-text('{STORE_SEARCH}')",
                    ]:
                        try:
                            loc = page.locator(sug_sel).first
                            if await loc.count() > 0:
                                await loc.click(timeout=2_000)
                                clicked_sug = True
                                break
                        except Exception:
                            pass

                    if not clicked_sug:
                        await page.keyboard.press("Enter")

                    # Attendre que les résultats de magasins chargent
                    try:
                        await page.wait_for_selector("text=Saint-Priest", timeout=6_000)
                    except Exception:
                        await page.wait_for_timeout(3_000)

                    # Cliquer le bouton "Choisir" dans la 1re carte résultat
                    clicked = False
                    for sel in [
                        "li button:has-text('Choisir')",
                        "[class*='journey'] button:has-text('Choisir')",
                        "[class*='store'] button:has-text('Choisir')",
                    ]:
                        try:
                            loc = page.locator(sel).first
                            if await loc.count() > 0:
                                await loc.scroll_into_view_if_needed(timeout=2_000)
                                await loc.click(timeout=3_000)
                                clicked = True
                                break
                        except Exception:
                            pass

                    if not clicked:
                        # Fallback JS
                        await page.evaluate("""() => {
                            const btn = [...document.querySelectorAll('button')]
                                .find(b => b.innerText.trim() === 'Choisir');
                            if (btn) { btn.scrollIntoView(); btn.click(); }
                        }""")

                    await page.wait_for_timeout(2_000)

                    # Confirmer la sélection si une modale de confirmation apparaît
                    try:
                        await page.wait_for_selector(
                            ".journeyConfirmation:has-text('Confirmer')", timeout=3_000
                        )
                        await page.locator(".journeyConfirmation:has-text('Confirmer')").click(timeout=3_000)
                        await page.wait_for_timeout(2_000)
                    except Exception:
                        pass

                # ── 3. Aller sur la page promos ───────────────────────────────
                await page.goto(
                    self.URL_PROMOS, wait_until="domcontentloaded", timeout=30_000
                )
                await page.wait_for_timeout(3_000)

                # Scroll + clic "Voir plus" jusqu'à épuisement du contenu
                prev_api = 0
                prev_dom = 0
                no_change_streak = 0
                _t0 = time.monotonic()
                for _i in range(80):
                    if self.is_cancelled() or (time.monotonic() - _t0) > 180:
                        print(f"[AUCHAN] Arrêt — {prev_dom} produits DOM")
                        break
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2_000)

                    # DEBUG première itération : voir les boutons après scroll
                    if _i == 0:
                        try:
                            btns_debug = await page.evaluate("""() =>
                                [...document.querySelectorAll('button, a')]
                                .map(b => b.innerText?.trim()).filter(t => t && t.length < 60)
                                .slice(-20)
                            """)
                            print(f"[AUCHAN DEBUG après scroll] Boutons bas: {btns_debug}")
                        except Exception:
                            pass

                    clicked = False
                    try:
                        clicked = await page.evaluate("""() => {
                            const btn = [...document.querySelectorAll('button, a')].find(b => {
                                const t = b.innerText?.trim().toLowerCase();
                                return t && (t.includes('voir plus') || t.includes('afficher plus')
                                          || t.includes('charger plus') || t.includes('load more'));
                            });
                            if (btn) { btn.click(); return true; }
                            return false;
                        }""")
                    except Exception:
                        pass
                    if clicked:
                        await page.wait_for_timeout(2_000)

                    dom_count = await page.evaluate(
                        "() => document.querySelectorAll(\"article[itemtype='http://schema.org/Product']\").length"
                    )
                    current = max(len(api_products), dom_count)
                    print(f"[AUCHAN] DOM:{dom_count} API:{len(api_products)}…")
                    if current == max(prev_api, prev_dom):
                        no_change_streak += 1
                        if no_change_streak >= 8:
                            break
                    else:
                        no_change_streak = 0
                    prev_api = len(api_products)
                    prev_dom = dom_count

                # ── 4. Produits : API en priorité, DOM en fallback ────────────
                if api_products:
                    print(f"[AUCHAN] Mapping {len(api_products)} produits API…")
                    seen: set[str] = set()
                    for product in api_products:
                        name = (
                            product.get("title") or product.get("name")
                            or product.get("label") or product.get("productTitle")
                        )
                        if not name or name in seen:
                            continue
                        seen.add(name)

                        price_info = product.get("price") or product.get("pricing") or {}
                        promo = (price_info.get("promotionalPrice") or price_info.get("salePrice")
                                 or price_info.get("value") or product.get("price"))
                        orig  = (price_info.get("regularPrice") or price_info.get("crossedPrice")
                                 or price_info.get("strikethroughPrice"))
                        disc  = (price_info.get("discountPercentage") or price_info.get("promotionRate")
                                 or product.get("discountPercentage"))

                        imgs = product.get("images") or product.get("imageList") or []
                        img = None
                        if isinstance(imgs, list) and imgs:
                            img = imgs[0].get("url") if isinstance(imgs[0], dict) else imgs[0]
                        elif isinstance(product.get("image"), str):
                            img = product["image"]

                        cats = product.get("categories") or product.get("category") or []
                        cat = "Autre"
                        if isinstance(cats, list) and cats:
                            last = cats[-1]
                            cat = last.get("label") or last.get("name") or last if isinstance(last, str) else "Autre"
                        elif isinstance(cats, str):
                            cat = cats

                        promos.append(self.make_promo(
                            name=str(name).strip(),
                            category=str(cat),
                            original_price=float(orig) if orig else None,
                            promo_price=float(promo) if promo else None,
                            discount_percent=float(str(disc).replace("%", "").replace("-", "")) if disc else None,
                            image_url=img,
                        ))
                else:
                    # Fallback DOM
                    print("[AUCHAN] Fallback DOM")
                    items = await page.evaluate("""() => {
                        return [...document.querySelectorAll(
                            "article[itemtype='http://schema.org/Product']"
                        )].map(card => {
                            const nameEl  = card.querySelector('[itemprop~="name"]');
                            const imgMeta = card.querySelector('meta[itemprop="image"]');
                            const imgEl   = card.querySelector('img[src*="cdn.auchan"], img[srcset*="cdn.auchan"], img');
                            const priceEl = card.querySelector(
                                '.product-thumbnail__price, [itemprop="price"], .price'
                            );
                            const origEl  = card.querySelector(
                                '.product-thumbnail__price--crossed, .old-price, s, del'
                            );
                            const discEl  = card.querySelector(
                                '[class*="discount"], [class*="reduction"], [class*="promo"]'
                            );
                            const badgeEl = card.querySelector(
                                '[class*="sticker"], [class*="badge"], [class*="label"], [class*="tag"]'
                            );
                            const linkEl  = card.querySelector('a[href]');
                            return {
                                name:  nameEl  ? nameEl.innerText.trim()  : null,
                                img:   imgMeta ? imgMeta.content : (imgEl ? imgEl.src : null),
                                price: priceEl ? priceEl.innerText.trim() : null,
                                orig:  origEl  ? origEl.innerText.trim()  : null,
                                disc:  discEl  ? discEl.innerText.trim()  : null,
                                badge: badgeEl ? badgeEl.innerText.trim() : null,
                                href:  linkEl  ? linkEl.getAttribute('href') : '',
                            };
                        }).filter(i => i.name && i.name.length > 1);
                    }""")
                    for item in items:
                        promos.append(self.make_promo(
                            name=item["name"],
                            category=self._category_from_href(item["href"] or ""),
                            original_price=self.parse_price(item["orig"]),
                            promo_price=self.parse_price(item["price"]),
                            discount_percent=self.parse_discount(item["disc"]),
                            image_url=item["img"],
                            description=item.get("badge"),
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
    def _category_from_href(href: str) -> str:
        # Les URLs Auchan ne contiennent pas la catégorie dans le chemin,
        # on inspecte donc le slug produit (nom en kebab-case).
        mapping = {
            # Épicerie / Boissons
            "cafe": "Épicerie", "biscuit": "Épicerie", "cereale": "Épicerie",
            "pate": "Épicerie", "riz": "Épicerie", "sauce": "Épicerie",
            "confiture": "Épicerie", "chocolat": "Épicerie", "farine": "Épicerie",
            "huile": "Épicerie", "vinaigre": "Épicerie", "conserve": "Épicerie",
            "eau": "Boissons", "jus": "Boissons", "soda": "Boissons",
            "biere": "Boissons", "vin": "Boissons", "boisson": "Boissons",
            # Frais / Surgelés
            "yaourt": "Frais", "lait": "Frais", "fromage": "Fromage",
            "beurre": "Frais", "creme": "Frais", "oeuf": "Frais",
            "surgele": "Surgelés", "glace": "Surgelés",
            # Viandes / Poissons
            "poulet": "Boucherie", "boeuf": "Boucherie", "porc": "Boucherie",
            "viande": "Boucherie", "steak": "Boucherie",
            "saumon": "Poissonnerie", "thon": "Poissonnerie", "poisson": "Poissonnerie",
            "jambon": "Charcuterie", "saucisse": "Charcuterie", "lardons": "Charcuterie",
            # Fruits & Légumes
            "tomate": "Fruits & Légumes", "pomme": "Fruits & Légumes",
            "banane": "Fruits & Légumes", "fruit": "Fruits & Légumes",
            "legume": "Fruits & Légumes", "salade": "Fruits & Légumes",
            # Hygiène / Entretien
            "papier-toilette": "Hygiène", "shampoo": "Hygiène", "shampoing": "Hygiène",
            "deodorant": "Hygiène", "dentifrice": "Hygiène", "savon": "Hygiène",
            "hygiene": "Hygiène", "couche": "Bébé", "bebe": "Bébé",
            "lessive": "Entretien", "entretien": "Entretien", "nettoyant": "Entretien",
            # Non-alimentaire
            "electromenager": "Électroménager", "informatique": "Électronique",
            "telephone": "Électronique", "tv": "Électronique",
            "textile": "Textile", "vetement": "Textile", "chaussure": "Textile",
            "jardin": "Jardin", "sport": "Sport", "jouet": "Jouets",
            "animal": "Animaux", "chat": "Animaux", "chien": "Animaux",
        }
        href_low = href.lower()
        for key, label in mapping.items():
            if key in href_low:
                return label
        return "Autre"
