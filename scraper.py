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
    Scrape les annonces PAP.fr selon les critères utilisateur.
    Retourne une liste d'annonces structurées.
    """

    # Construction de l'URL de recherche PAP
    url = (
        f"https://www.pap.fr/annonce/vente-appartement-maison-{ville.lower()}-g"
        f"?prix-max={prix_max}"
        f"&surface-min={surface_min}"
        f"&nb-pieces-min={nb_pieces}"
    )

    annonces = []

    try:
        # Pause aléatoire pour éviter le blocage
        time.sleep(random.uniform(1.5, 3.0))

        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Sélecteur des cartes d'annonces PAP
        cartes = soup.select("div.search-list-item")

        for carte in cartes[:20]:  # Limite à 20 annonces par run

            annonce = extraire_donnees_pap(carte)

            if annonce:
                # Calcul rentabilité immédiat
                annonce = calculer_rentabilite(annonce)
                annonces.append(annonce)

    except requests.RequestException as e:
        print(f"Erreur scraping PAP : {e}")

    return annonces


def extraire_donnees_pap(carte) -> dict:
    """
    Extrait les données d'une carte annonce PAP.
    Retourne un dict structuré ou None si données manquantes.
    """
    try:
        # Prix
        prix_tag = carte.select_one(".price")
        prix_texte = prix_tag.get_text(strip=True) if prix_tag else ""
        prix = extraire_nombre(prix_texte)

        # Surface
        surface_tag = carte.select_one(".criteria-item-area")
        surface_texte = surface_tag.get_text(strip=True) if surface_tag else ""
        surface = extraire_nombre(surface_texte)

        # Nombre de pièces
        pieces_tag = carte.select_one(".criteria-item-room")
        pieces_texte = pieces_tag.get_text(strip=True) if pieces_tag else ""
        pieces = extraire_nombre(pieces_texte)

        # Titre / description
        titre_tag = carte.select_one("h2.title")
        titre = titre_tag.get_text(strip=True) if titre_tag else "Sans titre"

        # Localisation
        lieu_tag = carte.select_one(".item-description .location")
        localisation = lieu_tag.get_text(strip=True) if lieu_tag else "Non précisé"

        # URL de l'annonce
        lien_tag = carte.select_one("a.item-link")
        url_annonce = (
            "https://www.pap.fr" + lien_tag["href"]
            if lien_tag and lien_tag.get("href")
            else ""
        )

        # DPE (si disponible)
        dpe_tag = carte.select_one(".dpe-letter")
        dpe = dpe_tag.get_text(strip=True) if dpe_tag else "Non communiqué"

        # Validation : on rejette les annonces sans prix ni surface
        if not prix or not surface:
            return None

        return {
            "source": "PAP",
            "titre": titre,
            "prix": prix,
            "surface": surface,
            "pieces": pieces or 0,
            "localisation": localisation,
            "dpe": dpe,
            "url": url_annonce,
            "prix_m2": round(prix / surface, 0) if surface > 0 else 0,
        }

    except Exception as e:
        print(f"Erreur extraction carte : {e}")
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
