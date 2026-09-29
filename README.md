# PROJET ODP - Plateforme de gestion dynamique de conteneurs Docker

Ce projet consiste en une plateforme de gestion dynamique de conteneurs Docker pour fournir des environnements isolés destinés au pentesting et à l'analyse de sécurité.

## Démarrage Rapide (Control Plane Flask + PostgreSQL)

1. Copier `.env.example` en `.env`. Pour lancer Flask hors Docker, mettre `localhost` au lieu de `postgres` dans `DATABASE_URL`.
2. Lancer la base de données PostgreSQL via Docker Compose :
   ```bash
   docker compose up -d postgres
   ```
3. Installer les dépendances Python :
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Créer les tables (migrations Alembic) et remplir le catalogue des distributions :
   ```bash
   export FLASK_APP=run.py
   flask db upgrade
   flask seed
   ```
5. Lancer l'application : `python run.py` → http://127.0.0.1:5001

Tant que le Worker Agent n'existe pas, on simule un Worker à la main :
```bash
curl -X POST http://127.0.0.1:5001/workers/register -H "Content-Type: application/json" \
  -d '{"hostname": "worker1", "ip_address": "192.168.56.11", "cpu_cores": 4, "ram_mb": 8192}'
```

## API

| Méthode | Route | Auth | Rôle |
|---|---|---|---|
| GET | `/health` | non | État du service |
| POST | `/register` · `/login` · `/logout` | – | Authentification (JSON `username`, `password`) |
| GET | `/distributions` | oui | Catalogue des images (Kali, Parrot) |
| GET | `/instances` | oui | Instances de l'utilisateur connecté |
| POST | `/rent` | oui | Location : `distribution_id`, `cpu`, `ram_mb`, `duration_minutes` → Instance `PENDING` |
| POST | `/instances/<id>/stop` | oui | Arrêt d'une instance (propriétaire uniquement) |
| GET | `/workers` | oui | Liste des Workers |
| POST | `/workers/register` | non | Enregistrement d'un Worker : `hostname`, `ip_address`, `cpu_cores`, `ram_mb` |
| POST | `/workers/heartbeat` | non | Heartbeat d'un Worker : `hostname` |

Chaque instance reçoit un nom unique (`lab-<user_id>-<hex>`, champ `name`) destiné au routage Traefik. Le champ `access_url` sera rempli une fois Traefik intégré.
