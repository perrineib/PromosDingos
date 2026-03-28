from fastapi import FastAPI, Depends, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional, List
import os

from .database import get_db, init_db, Promotion, SessionLocal

app = FastAPI(title="PromosDingo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- État global du scraping ---
scraping_status = {
    "running": False,
    "last_run": None,
    "message": "Jamais lancé",
    "count": 0,
    "stores": {},
}
cancel_requested = False

STORES = ["lidl", "carrefour", "auchan"]


@app.on_event("startup")
def startup():
    init_db()


# ─── API ────────────────────────────────────────────────────────────────────

@app.get("/api/promotions")
def get_promotions(
    store: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = "discount",   # discount | price_asc | price_desc | name
    db: Session = Depends(get_db),
):
    q = db.query(Promotion)
    if store:
        q = q.filter(Promotion.store == store)
    if category and category != "Toutes":
        q = q.filter(Promotion.category == category)
    if search:
        q = q.filter(Promotion.name.ilike(f"%{search}%"))

    if sort == "price_asc":
        q = q.order_by(Promotion.promo_price.asc())
    elif sort == "price_desc":
        q = q.order_by(Promotion.promo_price.desc())
    elif sort == "name":
        q = q.order_by(Promotion.name.asc())
    else:
        q = q.order_by(Promotion.discount_percent.desc())

    promos = q.all()
    return [_promo_to_dict(p) for p in promos]


@app.get("/api/categories")
def get_categories(db: Session = Depends(get_db)):
    rows = db.query(Promotion.category).distinct().all()
    return sorted([r[0] for r in rows if r[0]])


@app.get("/api/stores")
def get_stores(db: Session = Depends(get_db)):
    rows = (
        db.query(Promotion.store, func.count(Promotion.id))
        .group_by(Promotion.store)
        .all()
    )
    counts = {store: 0 for store in STORES}
    for store, cnt in rows:
        counts[store] = cnt
    return [{"store": s, "count": c} for s, c in counts.items()]


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(Promotion.id)).scalar() or 0
    avg_discount = db.query(func.avg(Promotion.discount_percent)).scalar() or 0

    by_store = (
        db.query(
            Promotion.store,
            func.count(Promotion.id).label("count"),
            func.avg(Promotion.discount_percent).label("avg_discount"),
            func.min(Promotion.promo_price).label("min_price"),
        )
        .group_by(Promotion.store)
        .all()
    )

    by_category = (
        db.query(Promotion.category, func.count(Promotion.id))
        .group_by(Promotion.category)
        .order_by(func.count(Promotion.id).desc())
        .all()
    )

    # Produits présents dans plusieurs enseignes (matching par nom normalisé)
    subq = (
        db.query(
            func.lower(Promotion.name).label("norm_name"),
            func.count(func.distinct(Promotion.store)).label("store_count"),
            func.min(Promotion.promo_price).label("best_price"),
            func.max(Promotion.discount_percent).label("best_discount"),
        )
        .group_by(func.lower(Promotion.name))
        .having(func.count(func.distinct(Promotion.store)) > 1)
        .order_by(func.count(func.distinct(Promotion.store)).desc())
        .limit(20)
        .all()
    )

    # Top deals
    top_deals = (
        db.query(Promotion)
        .filter(Promotion.discount_percent.isnot(None))
        .order_by(Promotion.discount_percent.desc())
        .limit(10)
        .all()
    )

    return {
        "total": total,
        "avg_discount": round(avg_discount, 1),
        "by_store": [
            {
                "store": s,
                "count": c,
                "avg_discount": round(a or 0, 1),
                "min_price": mp,
            }
            for s, c, a, mp in by_store
        ],
        "by_category": [
            {"category": cat, "count": cnt} for cat, cnt in by_category if cat
        ],
        "multi_store": [
            {
                "name": r.norm_name,
                "store_count": r.store_count,
                "best_price": r.best_price,
                "best_discount": round(r.best_discount or 0, 1),
            }
            for r in subq
        ],
        "top_deals": [_promo_to_dict(p) for p in top_deals],
    }


@app.post("/api/refresh")
async def refresh(
    background_tasks: BackgroundTasks,
    stores: Optional[str] = Query(default=None),
):
    if scraping_status["running"]:
        return {"message": "Scraping déjà en cours", "running": True}

    store_list = stores.split(",") if stores else None
    background_tasks.add_task(_do_scraping, store_list)
    return {"message": "Scraping lancé", "running": True}


@app.get("/api/refresh/status")
def refresh_status():
    return scraping_status


@app.post("/api/refresh/cancel")
def cancel_refresh():
    global cancel_requested
    cancel_requested = True
    return {"message": "Annulation demandée"}


# ─── Static / SPA ───────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ─── Helpers ────────────────────────────────────────────────────────────────

def _promo_to_dict(p: Promotion) -> dict:
    return {
        "id": p.id,
        "store": p.store,
        "name": p.name,
        "category": p.category,
        "original_price": p.original_price,
        "promo_price": p.promo_price,
        "discount_percent": p.discount_percent,
        "image_url": p.image_url,
        "description": p.description,
        "valid_from": p.valid_from,
        "valid_until": p.valid_until,
        "scraped_at": p.scraped_at.isoformat() if p.scraped_at else None,
    }


async def _do_scraping(stores: Optional[List[str]] = None):
    global scraping_status, cancel_requested
    cancel_requested = False
    target = stores or STORES

    stores_status = {s: {"status": "pending", "count": 0} for s in target}
    scraping_status = {
        "running": True,
        "last_run": None,
        "message": "Démarrage...",
        "count": 0,
        "stores": stores_status,
    }

    db = SessionLocal()
    total = 0
    try:
        from .scrapers import SCRAPER_MAP, _safe_scrape

        for store in target:
            if cancel_requested:
                for s in target:
                    if stores_status[s]["status"] == "pending":
                        stores_status[s]["status"] = "annulé"
                scraping_status["message"] = f"Annulé — {total} promotions conservées"
                scraping_status["running"] = False
                scraping_status["last_run"] = datetime.utcnow().isoformat()
                break

            stores_status[store]["status"] = "running"
            scraping_status["message"] = f"Scraping {store}…"
            scraping_status["stores"] = dict(stores_status)

            # Supprime uniquement cette enseigne juste avant de la rescaper
            db.query(Promotion).filter(Promotion.store == store).delete()
            db.commit()

            scraper_cls = SCRAPER_MAP.get(store)
            results = await _safe_scrape(store, scraper_cls(cancel_fn=lambda: cancel_requested)) if scraper_cls else []

            for promo_data in results:
                db.add(Promotion(**promo_data))
            db.commit()

            stores_status[store] = {"status": "done", "count": len(results)}
            total += len(results)
            scraping_status["count"] = total
            scraping_status["stores"] = dict(stores_status)

        else:
            scraping_status["running"] = False
            scraping_status["last_run"] = datetime.utcnow().isoformat()
            scraping_status["message"] = f"{total} promotions récupérées"

    except Exception as e:
        db.rollback()
        scraping_status.update({
            "running": False,
            "last_run": datetime.utcnow().isoformat(),
            "message": f"Erreur : {e}",
        })
    finally:
        db.close()
