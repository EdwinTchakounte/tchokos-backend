# Tchokos — Backend (Django + Wagtail)

API headless et back-offices de la plateforme **Tchokos** (vitrine e-commerce
chaussures & vêtements, Douala — Cameroun). Consommé par le frontend Next.js
(dépôt séparé `tchokos-frontend`).

## Stack
- **Django 5.1** + **Wagtail 6.3** (CMS éditorial)
- **Django REST Framework** (API catalogue / commandes / contact)
- **Brevo** (emails transactionnels) — `integrations/brevo.py`
- **Tara Money** (paiement Mobile Money, branché en phase 2) — `integrations/tara.py`
- SQLite en dev (Postgres recommandé en prod)

## Architecture

| Espace | URL | Pour qui |
|---|---|---|
| Back-office produits & commandes | `/gestion/` | Équipe Tchokos (admin Django épuré) |
| CMS éditorial (pages, réglages marque) | `/cms/` | Éditeurs de contenu (Wagtail) |
| API REST (catalogue, commande, contact) | `/api/` | Frontend Next.js |
| API CMS (pages Wagtail) | `/api/cms/` | Frontend Next.js |

### Apps
- `catalog` — Catégories, Produits, Photos (back-office produits dédié)
- `orders` — Commandes / leads WhatsApp (donnée client) + hook paiement
- `siteconfig` — Réglages marque éditables dans Wagtail (WhatsApp, adresse, réseaux)
- `integrations` — Brevo (email), Tara Money (paiement)
- `api` — Serializers + endpoints DRF
- `home` — Pages Wagtail (accueil, à propos)

## Démarrage

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # puis renseigner BREVO_API_KEY, etc.
export DJANGO_SETTINGS_MODULE=tchokos.settings.dev

python manage.py migrate
python manage.py seed_demo     # catégories + produits + images de démo
python manage.py createsuperuser
python manage.py runserver
```

- Back-office produits : http://localhost:8000/gestion/
- CMS Wagtail : http://localhost:8000/cms/
- API : http://localhost:8000/api/products/

## Endpoints API principaux

| Méthode | URL | Description |
|---|---|---|
| GET | `/api/categories/` | Liste des catégories |
| GET | `/api/products/` | Produits (filtres : `?category=`, `?target=`, `?featured=1`, `?search=`) |
| GET | `/api/products/<slug>/` | Détail produit |
| GET | `/api/site-config/` | Marque & contact (WhatsApp, réseaux) |
| POST | `/api/orders/` | Crée une commande, renvoie un lien WhatsApp pré-rempli |
| POST | `/api/contact/` | Formulaire de contact (email via Brevo) |

## Intégrations

- **Brevo** : renseigner `BREVO_API_KEY`. Sans clé, les emails sont loggés (no-op) —
  le développement n'est pas bloqué.
- **Tara Money** : `integrations/tara.py` pose l'architecture. En phase 1 la
  commande passe par WhatsApp ; `create_payment_link` renvoie un lien stub tant
  que `TARA_API_KEY`/`TARA_MERCHANT_ID` ne sont pas configurés.
