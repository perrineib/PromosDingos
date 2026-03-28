# 🛒 PromosDingo

Comparateur de promotions hebdomadaires des grandes surfaces françaises.
L'app scrape automatiquement les promos de Lidl, Carrefour et Auchan, les stocke en base, et les affiche avec filtres par enseigne et catégorie.

## Fonctionnalités

- **Scraping automatique** de Lidl, Carrefour et Auchan via Playwright (simulation navigateur)
- **Filtrage** par enseigne, catégorie et recherche textuelle
- **Tri** par meilleure réduction, prix croissant/décroissant ou nom
- **Informations produit** : prix promo, prix barré, % de réduction, image, description de l'offre
- **Catégorisation automatique** des produits (Épicerie sucrée/salée, Boissons, Produits frais, Surgelés, Viande, Poissons, Fruits & Légumes, Hygiène, Entretien…)
- **Onglet Statistiques** : graphiques par enseigne/catégorie, top deals, produits présents dans plusieurs enseignes
- **Bouton Arrêter** pour interrompre le scraping en cours
- **Horodatage** de la dernière mise à jour

## Stack

| Couche | Technologie |
|--------|-------------|
| Backend | FastAPI + SQLite (SQLAlchemy) |
| Scraping | Playwright (async) |
| Frontend | Vanilla JS SPA + Chart.js |
| Package manager | uv |

## Installation

**Prérequis** : Python 3.11+, [uv](https://github.com/astral-sh/uv)

```bash
# Cloner le repo
git clone https://github.com/TON_USER/PromosDingo.git
cd PromosDingo

# Créer l'environnement virtuel et installer les dépendances
uv venv env_promosdingo
uv pip install -r requirements.txt

# Installer Chromium pour Playwright
python -m playwright install chromium
```

## Lancement

```bash
# Activer l'environnement (Windows)
env_promosdingo\Scripts\activate

# Démarrer le serveur
python run.py
```

L'application est accessible sur [http://localhost:8000](http://localhost:8000).

## Utilisation

1. Ouvrir [http://localhost:8000](http://localhost:8000)
2. Cliquer sur **Tout** pour scraper les 3 enseignes (ou choisir une enseigne spécifique)
3. Attendre la fin du scraping (~5 minutes pour les 3 enseignes)
4. Filtrer par enseigne, catégorie ou mot-clé

## Structure du projet

```
PromosDingo/
├── backend/
│   ├── main.py          # API FastAPI + orchestration scraping
│   ├── database.py      # Modèle SQLAlchemy
│   └── scrapers/
│       ├── base.py      # Classe de base + taxonomie catégories
│       ├── lidl.py      # Scraper Lidl (interception API)
│       ├── carrefour.py # Scraper Carrefour (interception API)
│       └── auchan.py    # Scraper Auchan (scroll DOM)
├── frontend/
│   └── index.html       # SPA complète (HTML + CSS + JS)
├── requirements.txt
└── run.py               # Point d'entrée
```

## Notes

- Aldi et Intermarché ne sont pas supportés (catalogue flipbook / protection anti-bot)
- Le scraping peut varier selon la disponibilité des sites
