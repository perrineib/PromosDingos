"""
Orchestrateur des scrapers.
Chaque scraper renvoie une liste de dicts correspondant au modèle Promotion.
"""
import asyncio
from typing import List, Optional

from .lidl import LidlScraper
from .carrefour import CarrefourScraper
from .auchan import AuchanScraper

SCRAPER_MAP = {
    "lidl": LidlScraper,
    "carrefour": CarrefourScraper,
    "auchan": AuchanScraper,
}


async def _safe_scrape(store: str, scraper) -> List[dict]:
    """Encapsule le scraper pour ne jamais faire planter l'orchestrateur."""
    try:
        print(f"[{store.upper()}] Démarrage...")
        promos = await scraper.scrape()
        print(f"[{store.upper()}] {len(promos)} promotions trouvées.")
        return promos
    except Exception as e:
        print(f"[{store.upper()}] Erreur : {e}")
        return []
