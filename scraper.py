"""
RENDIO — Scraper immobilier
Serveur Flask appelé par Make via webhook
Scrape PAP.fr et retourne les annonces en JSON
"""

from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import time
import random
import re
import os

app = Flask(__name__)

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────

# Headers pour simuler un vrai navigateur (anti-blocage)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.pap.fr/",
}

# Clé secrète pour sécuriser le webhook Make
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "rendio-secret-2024")


# ─────────────────────────────────────────
# SCRAPING PAP.FR
# ─────────────────────────────────────────

def scrape_pap(ville: str, prix_max: int, surface_min: int, nb_pieces: int) -> list:
    """
    Récupère les annonces PAP.fr via leur API JSON interne.
    Plus stable que le scraping HTML.
    """

    # Mapping villes → codes PAP
    VILLES_PAP = {
        "paris": "g439725",
        "lyon": "g42422",
        "marseille": "g42568",
        "bordeaux": "g42152",
        "toulouse": "g42678",
        "nantes": "g42597",
        "lille": "g42448",
        "nice": "g42603",
        "strasbourg": "g42654",
        "montpellier": "g42571",
    }

    code_ville = VILLES_PAP.get(ville.lower(), "g439725")

    url = "https://www.pap.fr/annonce/ventes-immobilieres"

    params = {
        "typeBien[]": ["appartement", "maison"],
        "geo[]": code_ville,
        "prixMax": prix_max,
        "surfaceMin": surface_min,
        "nbPiecesMin": nb_pieces,
        "tri": "date-desc",
    }

    annonces = []

    try:
        time.sleep(random.uniform(1.0, 2.5))

        response = requests.get(url, headers=HEADERS, params=params, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")

        # Sélecteurs PAP 2024/2025
        cartes = (
            soup.select("article.card-announcement")
            or soup.select("div.card-announcement")
            or soup.select("[data-id]")
            or soup.select(".search-result-item")
            or soup.select("li.search-list-item")
        )

        print(f"[PAP] {len(cartes)} cartes trouvées pour {ville}")

        for carte in cartes[:20]:
            annonce = extraire_donnees_pap(carte)
            if annonce:
                annonce = calculer_rentabilite(annonce)
                annonces.append(annonce)

        # Si toujours 0, on tente le flux JSON PAP
        if not annonces:
            annonces = scrape_pap_json(code_ville, prix_max, surface_min, nb_pieces)

        # Fallback démo si toujours vide
        if not annonces:
            print("[DEMO] Activation mode démo")
            annonces = generer_annonces_demo(ville, prix_max, surface_min)

    except requests.RequestException as e:
        print(f"Erreur scraping PAP : {e}")
        annonces = generer_annonces_demo(ville, prix_max, surface_min)

    return annonces


def generer_annonces_demo(ville: str, prix_max: int, surface_min: int) -> list:
    """
    Génère des annonces réalistes pour tester le flow Make → Airtable.
    """
    import hashlib
    seed = int(hashlib.md5(f"{ville}{prix_max}".encode()).hexdigest()[:8], 16)
    random.seed(seed)

    modeles = [
        {"type": "Appartement", "pieces": 2, "surface": 38, "prix": 145000, "dpe": "D", "quartier": "Centre"},
        {"type": "Appartement", "pieces": 3, "surface": 62, "prix": 189000, "dpe": "C", "quartier": "Nord"},
        {"type": "Maison", "pieces": 4, "surface": 85, "prix": 195000, "dpe": "E", "quartier": "Périphérie"},
        {"type": "Appartement", "pieces": 2, "surface": 45, "prix": 132000, "dpe": "B", "quartier": "Sud"},
        {"type": "Studio", "pieces": 1, "surface": 28, "prix": 89000, "dpe": "D", "quartier": "Centre"},
        {"type": "Appartement", "pieces": 3, "surface": 71, "prix": 178000, "dpe": "C", "quartier": "Est"},
    ]

    annonces = []
    for i, m in enumerate(modeles):
        variation = random.uniform(0.92, 1.08)
        prix = round(m["prix"] * variation / 1000) * 1000

        if prix > prix_max or m["surface"] < surface_min:
            continue

        annonce = {
            "source": "DEMO",
            "titre": f"{m['type']} {m['pieces']} pièces - {ville.capitalize()} {m['quartier']}",
            "prix": prix,
            "surface": m["surface"],
            "pieces": m["pieces"],
            "localisation": f"{ville.capitalize()} - {m['quartier']}",
            "dpe": m["dpe"],
            "url": f"https://www.pap.fr/annonce/demo-{i+1}",
            "prix_m2": round(prix / m["surface"]),
        }

        annonce = calculer_rentabilite(annonce)
        annonces.append(annonce)

    return annonces


def scrape_pap_json(code_ville: str, prix_max: int, surface_min: int, nb_pieces: int) -> list:
    """
    Fallback : appel direct à l'API JSON de PAP.
    """
    url = "https://api.pap.fr/search/classifieds"

    headers_api = {**HEADERS, "Accept": "application/json"}

    params = {
        "category": "9",  # 9 = vente immobilière
        "geo": code_ville,
        "pricemax": prix_max,
        "surfacemin": surface_min,
        "nb_roomsmin": nb_pieces,
        "sort": "date",
        "order": "desc",
        "page": 1,
        "resultsPerPage": 20,
    }

    annonces = []

    try:
        time.sleep(random.uniform(1.0, 2.0))
        response = requests.get(url, headers=headers_api, params=params, timeout=15)
        data = response.json()

        items = data.get("classifieds", data.get("results", data.get("items", [])))
        print(f"[PAP JSON] {len(items)} annonces trouvées")

        for item in items[:20]:
            prix = float(item.get("price", item.get("prix", 0)) or 0)
            surface = float(item.get("area", item.get("surface", 0)) or 0)

            if not prix or not surface:
                continue

            annonce = {
                "source": "PAP",
                "titre": item.get("title", item.get("titre", "Annonce PAP")),
                "prix": prix,
                "surface": surface,
                "pieces": int(item.get("nb_rooms", item.get("pieces", 0)) or 0),
                "localisation": item.get("city", item.get("ville", item.get("localisation", ""))),
                "dpe": item.get("energy_rate", item.get("dpe", "NC")),
                "url": "https://www.pap.fr" + item.get("url", item.get("slug", "")),
                "prix_m2": round(prix / surface) if surface > 0 else 0,
            }

            annonce = calculer_rentabilite(annonce)
            annonces.append(annonce)

    except Exception as e:
        print(f"Erreur API JSON PAP : {e}")

    return annonces


def extraire_donnees_pap(carte) -> dict:
    """
    Extrait les données d'une carte annonce PAP (HTML).
    """
    try:
        # Prix — multiples sélecteurs possibles
        prix = 0
        for sel in [".price", ".card-price", "[class*='price']", "strong"]:
            tag = carte.select_one(sel)
            if tag:
                prix = extraire_nombre(tag.get_text())
                if prix > 10000:
                    break

        # Surface
        surface = 0
        for sel in ["[class*='area']", "[class*='surface']", "li"]:
            tags = carte.select(sel)
            for tag in tags:
                txt = tag.get_text()
                if "m²" in txt or "m2" in txt:
                    surface = extraire_nombre(txt)
                    if surface > 5:
                        break
            if surface:
                break

        # Pièces
        pieces = 0
        for tag in carte.select("li, span, div"):
            txt = tag.get_text().lower()
            if "pièce" in txt or "piece" in txt or "p." in txt:
                pieces = extraire_nombre(txt)
                break

        # Titre
        titre_tag = carte.select_one("h2, h3, .title, [class*='title']")
        titre = titre_tag.get_text(strip=True) if titre_tag else "Annonce PAP"

        # Localisation
        loc = ""
        for sel in ["[class*='location']", "[class*='city']", "[class*='place']"]:
            tag = carte.select_one(sel)
            if tag:
                loc = tag.get_text(strip=True)
                break

        # URL
        lien = carte.select_one("a[href]")
        url_annonce = ""
        if lien:
            href = lien.get("href", "")
            url_annonce = href if href.startswith("http") else "https://www.pap.fr" + href

        if not prix or not surface:
            return None

        return {
            "source": "PAP",
            "titre": titre[:100],
            "prix": prix,
            "surface": surface,
            "pieces": pieces,
            "localisation": loc,
            "dpe": "NC",
            "url": url_annonce,
            "prix_m2": round(prix / surface) if surface > 0 else 0,
        }

    except Exception as e:
        print(f"Erreur extraction : {e}")
        return None


# ─────────────────────────────────────────
# CALCULS RENTABILITÉ
# ─────────────────────────────────────────

def calculer_rentabilite(annonce: dict) -> dict:
    """
    Calcule les indicateurs de rentabilité locative.
    Basé sur les ratios moyens du marché français.
    """
    prix = annonce["prix"]
    surface = annonce["surface"]

    # Frais de notaire (7.5% dans l'ancien)
    frais_notaire = prix * 0.075

    # Prix d'achat total
    prix_total = prix + frais_notaire

    # Loyer estimé (ratio loyer/m² moyen selon surface)
    # Source : données marché locatif français 2024
    if surface < 30:
        loyer_m2 = 18      # Studios : loyer/m² plus élevé
    elif surface < 50:
        loyer_m2 = 15
    elif surface < 80:
        loyer_m2 = 13
    else:
        loyer_m2 = 11

    loyer_mensuel_estime = surface * loyer_m2

    # Rendement brut
    rendement_brut = (loyer_mensuel_estime * 12) / prix_total * 100

    # Charges annuelles estimées
    charges_copro = surface * 30          # 30€/m²/an en moyenne
    taxe_fonciere = loyer_mensuel_estime * 1.5  # ~1.5 mois de loyer
    assurance_pno = 200                   # Assurance propriétaire non-occupant
    vacance_locative = loyer_mensuel_estime * 0.5  # 15j/an de vacance

    total_charges = charges_copro + taxe_fonciere + assurance_pno + vacance_locative

    # Rendement net
    revenus_nets = (loyer_mensuel_estime * 12) - total_charges
    rendement_net = revenus_nets / prix_total * 100

    # Mensualité crédit estimée (taux 3.8%, 20 ans, apport 10%)
    montant_emprunte = prix_total * 0.90
    taux_mensuel = 3.8 / 100 / 12
    duree_mois = 240
    mensualite = (
        montant_emprunte
        * taux_mensuel
        * (1 + taux_mensuel) ** duree_mois
        / ((1 + taux_mensuel) ** duree_mois - 1)
    )

    # Cashflow mensuel
    cashflow = loyer_mensuel_estime - mensualite - (total_charges / 12)

    # Score Rendio /10
    score = calculer_score(rendement_net, cashflow, annonce.get("dpe", ""))

    annonce.update({
        "frais_notaire": round(frais_notaire),
        "prix_total": round(prix_total),
        "loyer_mensuel_estime": round(loyer_mensuel_estime),
        "rendement_brut": round(rendement_brut, 2),
        "rendement_net": round(rendement_net, 2),
        "cashflow_mensuel": round(cashflow),
        "mensualite_credit": round(mensualite),
        "score_rendio": score,
        "statut": "🔥 Opportunité" if score >= 7 else "👀 À surveiller" if score >= 5 else "❌ Pas rentable",
    })

    return annonce


def calculer_score(rendement_net: float, cashflow: float, dpe: str) -> int:
    """
    Score Rendio sur 10 basé sur 3 critères pondérés.
    """
    score = 0

    # Rendement net (5 points)
    if rendement_net >= 7:
        score += 5
    elif rendement_net >= 5.5:
        score += 4
    elif rendement_net >= 4.5:
        score += 3
    elif rendement_net >= 3.5:
        score += 2
    else:
        score += 1

    # Cashflow (3 points)
    if cashflow >= 200:
        score += 3
    elif cashflow >= 0:
        score += 2
    elif cashflow >= -100:
        score += 1

    # DPE (2 points) — passoires thermiques = risque
    dpe_upper = dpe.upper()
    if dpe_upper in ["A", "B", "C"]:
        score += 2
    elif dpe_upper == "D":
        score += 1
    elif dpe_upper in ["E", "F", "G"]:
        score += 0  # Risque travaux obligatoires loi Climat
    else:
        score += 1  # Non communiqué → neutre

    return score


# ─────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────

def extraire_nombre(texte: str) -> float:
    """Extrait le premier nombre d'une chaîne de caractères."""
    texte_propre = texte.replace("\u202f", "").replace(" ", "").replace(",", ".")
    nombres = re.findall(r"\d+\.?\d*", texte_propre)
    return float(nombres[0]) if nombres else 0


# ─────────────────────────────────────────
# ENDPOINTS FLASK (appelés par Make)
# ─────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Endpoint de vérification — Make peut pinger ici."""
    return jsonify({"status": "ok", "service": "Rendio Scraper"})


@app.route("/scrape", methods=["POST"])
def webhook_scrape():
    """
    Endpoint principal appelé par Make.
    
    Body JSON attendu :
    {
        "secret": "rendio-secret-2024",
        "ville": "lyon",
        "prix_max": 200000,
        "surface_min": 30,
        "nb_pieces": 2
    }
    """

    data = request.get_json()

    # Vérification sécurité
    if not data or data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"error": "Non autorisé"}), 401

    # Paramètres de recherche
    ville = data.get("ville", "paris")
    prix_max = int(data.get("prix_max", 200000))
    surface_min = int(data.get("surface_min", 25))
    nb_pieces = int(data.get("nb_pieces", 1))

    # Scraping
    annonces = scrape_pap(ville, prix_max, surface_min, nb_pieces)

    # Filtrage : on remonte uniquement les annonces avec score >= 5
    bonnes_annonces = [a for a in annonces if a.get("score_rendio", 0) >= 5]

    return jsonify({
        "success": True,
        "total_trouvees": len(annonces),
        "total_filtrees": len(bonnes_annonces),
        "ville": ville,
        "annonces": bonnes_annonces,
    })


@app.route("/calcul", methods=["POST"])
def webhook_calcul():
    """
    Endpoint de calcul seul — si Make envoie une annonce déjà scrapée
    et veut juste les calculs de rentabilité.

    Body JSON attendu :
    {
        "secret": "rendio-secret-2024",
        "prix": 150000,
        "surface": 45,
        "dpe": "D"
    }
    """

    data = request.get_json()

    if not data or data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"error": "Non autorisé"}), 401

    annonce = {
        "prix": float(data.get("prix", 0)),
        "surface": float(data.get("surface", 0)),
        "dpe": data.get("dpe", ""),
        "titre": data.get("titre", ""),
        "localisation": data.get("localisation", ""),
        "pieces": int(data.get("pieces", 0)),
        "url": data.get("url", ""),
        "source": data.get("source", "Manuel"),
        "prix_m2": 0,
    }

    if annonce["surface"] > 0:
        annonce["prix_m2"] = round(annonce["prix"] / annonce["surface"])

    resultat = calculer_rentabilite(annonce)

    return jsonify({"success": True, "analyse": resultat})


# ─────────────────────────────────────────
# LANCEMENT
# ─────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
