"""
Classe de base pour tous les scrapers.
Fournit un navigateur Playwright partagé et des utilitaires communs.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
import re


class BaseScraper(ABC):
    """
    Sous-classe ce scraper pour chaque enseigne.
    Implémente la méthode `scrape()` qui renvoie une liste de dicts.

    Chaque dict doit contenir les clés :
        store, name, category, original_price, promo_price,
        discount_percent, image_url, description, valid_from, valid_until
    """

    STORE_NAME: str = ""   # à définir dans chaque sous-classe

    def __init__(self, cancel_fn=None):
        self._cancel_fn = cancel_fn

    def is_cancelled(self) -> bool:
        """Retourne True si l'annulation a été demandée."""
        return bool(self._cancel_fn and self._cancel_fn())

    # User-agent réaliste pour éviter les blocages basiques
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    @abstractmethod
    async def scrape(self) -> List[dict]:
        """Retourne la liste des promotions."""
        ...

    # ── Utilitaires ──────────────────────────────────────────────────────────

    # ── Taxonomie de catégories ───────────────────────────────────────────────

    _CATEGORY_RULES: list[tuple[str, list[str]]] = [
        ("Surgelés",              ["surgel", "congel", "sorbet"]),
        ("Épicerie sucrée",       ["biscuit", "chocolat", "cereale", "muesli", "confiture",
                                   "miel", "bonbon", "caramel", "gateau", "patisserie",
                                   "cookie", "tarte sucr", "compote", "speculoos", "nutella",
                                   "kinder", "haribo", "twix", "mars ", "snicker"]),
        ("Épicerie salée",        ["pate alim", "riz ", "semoule", "lentille", "pois chiche",
                                   "haricot", "conserve", "soupe", "sauce tomate", "huile d",
                                   "vinaigre", "moutarde", "ketchup", "mayonnaise", "chips",
                                   "crackers", "olive", "bouillon", "couscous"]),
        ("Boissons",              ["eau ", " jus ", "soda", "biere", " vin ", "champagne",
                                   "cidre", "limonade", " cafe", "the vert", "infusion",
                                   "boisson", "nectar", "whisky", "rhum", "vodka", "aperitif",
                                   "schweppes", "coca-", "pepsi", "orangina", "evian", "volvic"]),
        ("Produits frais",        ["yaourt", "yogourt", "skyr", "lait ", "beurre", "creme fraiche",
                                   "creme liquide", "margarine", " oeuf", "quiche",
                                   # fromages
                                   "fromage", "emmental", "gruyere", "comte", "cantal",
                                   "camembert", "brie", "roquefort", "mozzarella", "parmesan",
                                   "reblochon", "raclette", "beaufort", "munster", "feta",
                                   "chevre", "tome", "bleu d", "saint-nectaire", "maroilles",
                                   "epoisses", "livarot", "maasdam", "gouda", "edam",
                                   "mimolette", "abondance", "ossau", "fourme",
                                   "fromage blanc", "faisselle", "petit suisse"]),
        ("Viande & Charcuterie",  ["poulet", "boeuf", "porc", "agneau", "veau", "dinde",
                                   "steak", "escalope", "roti", "jambon", "saucisse",
                                   "saucisson", "lardon", "bacon", "chorizo", "rillette",
                                   "terrine", "merguez", "andouille"]),
        ("Poissons & Fruits de mer", ["saumon", "thon", "cabillaud", "sardine", "maquereau",
                                      "truite", "dorade", "crevette", "moule", "huitre",
                                      "colin", "lieu noir", "langouste", "homard"]),
        ("Fruits & Légumes",      [# fruits
                                   "pomme ", "poire", "banane", "orange", "citron",
                                   "fraise", "framboise", "myrtille", "cerise", "abricot",
                                   "prune", "peche", "nectarine", "brugnon", "raisin",
                                   "melon", "pasteque", "kiwi", "mangue", "ananas", "avocat",
                                   "clementine", "mandarine", "pamplemousse", "pomelo",
                                   "figue", "litchi", "grenade", "cassis", "groseille",
                                   "mure ", "physalis", "fruit ",
                                   # légumes
                                   "tomate", "salade", "carotte", "courgette", "poivron",
                                   "brocoli", "champignon", "epinard", "celeri", "fenouil",
                                   "poireau", "radis", "betterave", "artichaut", "asperge",
                                   "concombre", "haricot vert", "petit pois", "potiron",
                                   "courge", "patate douce", "aubergine", "oignon",
                                   "echalote", "ail ", "persil", "coriandre", "basilic",
                                   "legume"]),
        ("Hygiène & Beauté",      ["shampoo", "shampoing", "gel douche", "savon corps",
                                   "deodorant", "dentifrice", "brossea dent", "rasoir",
                                   "coton tige", "tampon", "serviette hygien", "maquillage",
                                   "fond de teint", "mascara", "parfum", "creme visage",
                                   "lotion", "serum", "demaquillant", "coloration"]),
        ("Entretien maison",      ["lessive", "liquide vaisselle", "nettoyant", "desinfectant",
                                   "detartrant", "deboucheur", "lave-vaisselle", "essuie-tout",
                                   "serpillere", "eponge", "sac poubelle", "papier essuie"]),
        ("Bébé",                  ["couche", "bebe", "biberon", "lait infantile",
                                   "lait 1er age", "lait 2eme age"]),
        ("Animaux",               ["croquette", "pate pour chien", "pate pour chat",
                                   "litiere", "aquarium"]),
        ("Electroménager",        ["electromenager", "robot cuisin", "mixeur", "cafetiere",
                                   "grille-pain", "aspirateur", "fer a repasser", "barbecue"]),
        ("High-Tech",             ["smartphone", "tablette", "ordinateur", "imprimante",
                                   "ecouteur", "casque audio", "television", "console de jeu",
                                   "appareil photo"]),
        ("Textile & Mode",        ["vetement", "chaussure", "chemise", "pantalon", "jean",
                                   "robe ", "manteau", "veste", "pull ", "t-shirt",
                                   "chaussette", "sous-vetement"]),
        ("Jardin & Bricolage",    ["jardin", "plante", "terreau", "tondeuse", "perceuse",
                                   "peinture mur", "bricolage"]),
        ("Sport & Loisirs",       ["sport", "velo", "trottinette", "ski ", "fitness",
                                   "yoga", "musculation", "raquette"]),
        ("Jouets & Jeux",         ["jouet", "lego", "puzzle", "peluche", "poupee",
                                   "jeu de societe", "deguisement"]),
        ("Maison & Déco",         ["deco", "decoration", "bougie", "coussin", "tapis",
                                   "etagere", "miroir"]),
    ]

    @staticmethod
    def infer_category(name: str, hint: str = "") -> str:
        """Infère la catégorie depuis le nom du produit (+ hint optionnel)."""
        text = (name + " " + hint).lower()
        for cat, keywords in BaseScraper._CATEGORY_RULES:
            for kw in keywords:
                if kw in text:
                    return cat
        return "Autre"

    def make_promo(
        self,
        name: str,
        category: str = "Autre",
        original_price: Optional[float] = None,
        promo_price: Optional[float] = None,
        discount_percent: Optional[float] = None,
        image_url: Optional[str] = None,
        description: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> dict:
        # Calcule la remise si elle manque mais qu'on a les deux prix
        if discount_percent is None and original_price and promo_price and original_price > 0:
            discount_percent = round((1 - promo_price / original_price) * 100, 1)

        # Infère la catégorie si absente
        if not category or category == "Autre":
            category = BaseScraper.infer_category(name)

        return {
            "store": self.STORE_NAME,
            "name": name.strip(),
            "category": category,
            "original_price": original_price,
            "promo_price": promo_price,
            "discount_percent": discount_percent,
            "image_url": image_url,
            "description": description,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }

    @staticmethod
    def parse_price(text: Optional[str]) -> Optional[float]:
        """Transforme '3,99 €' ou '3.99' en float."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d,.]", "", text).replace(",", ".")
        # S'il y a plusieurs points, garder le dernier
        parts = cleaned.split(".")
        if len(parts) > 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def parse_discount(text: Optional[str]) -> Optional[float]:
        """Extrait le pourcentage de réduction depuis '-30%' ou '30 %'."""
        if not text:
            return None
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
        if m:
            return float(m.group(1).replace(",", "."))
        return None

    @staticmethod
    async def new_browser_page(playwright, headless: bool = True):
        """Lance Chromium et renvoie (browser, page)."""
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=BaseScraper.USER_AGENT,
            locale="fr-FR",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        # Bloque les ressources inutiles pour aller plus vite
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
            lambda route: route.abort(),
        )
        return browser, page
