"""
PromosDingo - Lanceur de l'application

Prérequis (à faire une seule fois) :
    pip install -r requirements.txt
    playwright install chromium

Démarrage :
    python run.py
Puis ouvrir http://localhost:8000 dans le navigateur.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
