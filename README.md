# 🏠 RENDIO — Scraper Immobilier

Agent IA d'analyse locative — Module 1 : Scraping + Calculs

---

## 🚀 Déploiement sur Railway (5 min)

### Étape 1 — Créer un compte Railway
→ https://railway.app (gratuit jusqu'à 500h/mois)

### Étape 2 — Nouveau projet
1. "New Project" → "Deploy from GitHub repo"
2. Upload ces 3 fichiers : scraper.py / requirements.txt / Procfile
3. Railway détecte automatiquement Python

### Étape 3 — Variable d'environnement
Dans Railway → Settings → Variables :
```
WEBHOOK_SECRET = rendio-secret-2024   ← change ce mot de passe !
```

### Étape 4 — Récupérer ton URL
Railway te donne une URL du type :
```
https://rendio-scraper-production.up.railway.app
```

---

## 🔗 Config Make — Module HTTP

### Endpoint Scraping (nouvelles annonces)
```
Method  : POST
URL     : https://ton-url.railway.app/scrape
Headers : Content-Type: application/json

Body (JSON) :
{
  "secret": "rendio-secret-2024",
  "ville": "{{ville}}",
  "prix_max": {{prix_max}},
  "surface_min": {{surface_min}},
  "nb_pieces": {{nb_pieces}}
}
```

### Endpoint Calcul seul (annonce manuelle)
```
Method  : POST
URL     : https://ton-url.railway.app/calcul
Headers : Content-Type: application/json

Body (JSON) :
{
  "secret": "rendio-secret-2024",
  "prix": {{prix}},
  "surface": {{surface}},
  "dpe": "{{dpe}}",
  "localisation": "{{localisation}}"
}
```

### Endpoint Health Check
```
Method  : GET
URL     : https://ton-url.railway.app/health
→ Retourne {"status": "ok"} si tout tourne
```

---

## 📊 Données retournées par /scrape

```json
{
  "success": true,
  "total_trouvees": 18,
  "total_filtrees": 4,
  "ville": "lyon",
  "annonces": [
    {
      "source": "PAP",
      "titre": "Appartement 3 pièces Lyon 8",
      "prix": 180000,
      "surface": 62,
      "pieces": 3,
      "localisation": "Lyon 8e arrondissement",
      "dpe": "C",
      "url": "https://www.pap.fr/annonce/...",
      "prix_m2": 2903,
      "frais_notaire": 13500,
      "prix_total": 193500,
      "loyer_mensuel_estime": 806,
      "rendement_brut": 5.0,
      "rendement_net": 4.2,
      "cashflow_mensuel": -87,
      "mensualite_credit": 1012,
      "score_rendio": 6,
      "statut": "👀 À surveiller"
    }
  ]
}
```

---

## 🗺️ Flow Make complet (Semaine 1)

```
[Schedule : toutes les 2h]
        ↓
[HTTP POST → /scrape]
        ↓
[Iterator → pour chaque annonce]
        ↓
[Airtable → Create Record]
        ↓
[Filter : score_rendio >= 7]
        ↓
[Brevo → Envoyer email alerte]
```

---

## 🔧 Structure Airtable

Table : "Annonces"
Champs à créer :
- Titre (Text)
- Prix (Number)
- Surface (Number)
- Localisation (Text)
- DPE (Text)
- Rendement Net (Number)
- Cashflow Mensuel (Number)
- Score Rendio (Number)
- Statut (Single Select)
- URL Annonce (URL)
- Date Détection (Date)
- Source (Text)

---

## 📈 Prochaines étapes

- Semaine 2 → Ajouter SeLoger (nécessite Playwright)
- Semaine 3 → Appel Claude API pour analyse textuelle
- Semaine 4 → Rapport PDF + Brevo
- Semaine 5 → Interface Softr + Stripe
