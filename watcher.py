#!/usr/bin/env python3
"""
watcher.py - Surveillance temps réel et auto-réparation (séance 7, FONCTIONNALITÉS 07 et 13)

À placer à la racine du dépôt (à côté de run.py). Il tourne sur le Controller, dans la même
image que Flask, et pilote le Docker des Workers par SSH via app/provisioner.py.

À chaque cycle :
  1. Workers  : sans heartbeat depuis HEARTBEAT_TIMEOUT secondes -> OFFLINE (US26/US46).
  2. Failover : les instances actives d'un Worker OFFLINE sont recréées sur un autre Worker
                AVAILABLE ayant assez de CPU/RAM, puis mises à jour en base (US47 à US50).
  3. Conteneurs : une instance RUNNING dont le conteneur a planté (exited/dead/unhealthy)
                est relancée, MAX_RESTARTS fois au maximum. Au-delà : instance FAILED,
                location clôturée, conteneur et réseau supprimés. Le port publié par Docker
                change à chaque redémarrage : il est relu et mis à jour en base.
  4. /health  : petit serveur HTTP (WATCHER_HEALTH_PORT) pour le monitoring.

Seules les instances RUNNING (location ACTIVE et non expirée) sont surveillées : une instance
arrêtée par l'utilisateur (STOPPED) ou expirée n'est donc jamais relancée.

Variables d'environnement (en plus de celles de l'app : DATABASE_URL, DOCKER_MODE, ...) :
  WATCHER_INTERVAL_SECONDS   délai entre deux cycles (défaut 10)
  HEARTBEAT_TIMEOUT_SECONDS  délai avant OFFLINE (défaut 30)
  MAX_RESTARTS               relances avant FAILED (défaut 3)
  STABLE_SECONDS             durée de fonctionnement après laquelle le compteur repart à 0 (défaut 60)
  WATCHER_HEALTH_PORT        port de /health (défaut 8081)
"""
import json
import logging
import os
import re
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from docker.errors import NotFound
from sqlalchemy import or_

from app import create_app, provisioner
from app.models import db, utcnow, Worker, Instance, Rental

INTERVAL = int(os.environ.get("WATCHER_INTERVAL_SECONDS", 10))
HEARTBEAT_TIMEOUT = int(os.environ.get("HEARTBEAT_TIMEOUT_SECONDS", 30))
MAX_RESTARTS = int(os.environ.get("MAX_RESTARTS", 3))
STABLE_SECONDS = int(os.environ.get("STABLE_SECONDS", 60))
HEALTH_PORT = int(os.environ.get("WATCHER_HEALTH_PORT", 8081))

ACTIVE_STATUSES = ("PENDING", "RUNNING")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [watcher] %(message)s",
)
log = logging.getLogger("watcher")

stop_event = threading.Event()
health_state = {"last_ok": None}  # timestamp du dernier cycle réussi
restart_counts = {}  # container_id -> relances consécutives
_no_capacity_warned = set()  # instance_id déjà signalées (évite de spammer le log)


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def parse_docker_time(value):
    """Convertit '2026-10-07T15:00:00.123456789Z' (format Docker) en datetime UTC."""
    value = re.sub(r"(\.\d{1,6})\d*Z$", r"\1+00:00", value)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_stable(state):
    """Vrai si le conteneur tourne sans interruption depuis au moins STABLE_SECONDS."""
    started = state.get("StartedAt")
    if not started or started.startswith("0001"):
        return False
    try:
        age = (datetime.now(timezone.utc) - parse_docker_time(started)).total_seconds()
    except ValueError:
        return False
    return age >= STABLE_SECONDS


def host_port(container):
    """Port hôte publié pour le terminal web (7681/tcp), ou None."""
    try:
        return int(container.attrs["NetworkSettings"]["Ports"]["7681/tcp"][0]["HostPort"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def fail_instance(instance, reason):
    """Instance irrécupérable : base d'abord (FAILED + location clôturée), nettoyage Docker ensuite.

    FAILED est hors ACTIVE_STATUSES : l'utilisateur peut relouer immédiatement (même
    convention que /rent quand la création échoue).
    """
    log.error("%s : %s -> FAILED.", instance.name, reason)
    container_id = instance.container_id
    instance.status = "FAILED"
    instance.rental.status = "ENDED"
    db.session.commit()
    restart_counts.pop(container_id, None)
    try:
        provisioner.remove_container(instance)  # conteneur + réseau dédié ; no-op sans container_id
    except Exception as exc:
        log.error("%s : nettoyage Docker impossible (%s).", instance.name, exc)


# ---------------------------------------------------------------------------
# 1. Workers : heartbeat
# ---------------------------------------------------------------------------

def check_workers():
    limit = utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT)
    stale = Worker.query.filter(
        Worker.status != "OFFLINE",
        or_(Worker.last_heartbeat.is_(None), Worker.last_heartbeat < limit),
    ).all()
    for worker in stale:
        log.warning("ALERTE : aucun heartbeat de %s depuis plus de %ss -> OFFLINE.",
                    worker.hostname, HEARTBEAT_TIMEOUT)
        worker.status = "OFFLINE"
    if stale:
        db.session.commit()


# ---------------------------------------------------------------------------
# 2. Failover : instances d'un Worker OFFLINE
# ---------------------------------------------------------------------------

def pick_replacement(instance):
    """Worker AVAILABLE (autre que l'actuel) avec assez de CPU/RAM libres, le plus libre d'abord."""
    best = None
    candidates = Worker.query.filter(Worker.status == "AVAILABLE", Worker.id != instance.worker_id).all()
    for worker in candidates:
        used_cpu = sum(i.cpu_limit for i in worker.instances if i.status in ACTIVE_STATUSES)
        used_ram = sum(i.ram_limit_mb for i in worker.instances if i.status in ACTIVE_STATUSES)
        free_cpu = worker.cpu_cores - used_cpu
        free_ram = worker.ram_mb - used_ram
        if free_cpu >= instance.cpu_limit and free_ram >= instance.ram_limit_mb:
            if best is None or free_cpu > best[0]:
                best = (free_cpu, worker)
    return best[1] if best else None


def recover_orphans():
    """Recrée sur un autre Worker les instances actives portées par un Worker OFFLINE (idempotent)."""
    orphans = (
        Instance.query.join(Rental).join(Worker)
        .filter(
            Worker.status == "OFFLINE",
            Instance.status.in_(ACTIVE_STATUSES),
            Rental.status == "ACTIVE",
            Rental.end_time > utcnow(),
        )
        .all()
    )
    for instance in orphans:
        old_hostname = instance.worker.hostname
        target = pick_replacement(instance)
        if target is None:
            if instance.id not in _no_capacity_warned:
                log.warning("%s : %s est OFFLINE et aucun Worker n'a assez de ressources "
                            "pour la reprendre. Nouvel essai au prochain cycle.",
                            instance.name, old_hostname)
                _no_capacity_warned.add(instance.id)
            continue

        # L'ancien conteneur est injoignable : on libère container_id (UNIQUE) et on repart de zéro.
        instance.worker = target
        instance.container_id = None
        instance.port = None
        instance.status = "PENDING"
        db.session.commit()
        _no_capacity_warned.discard(instance.id)

        try:
            container_id, port = provisioner.create_container(instance)
        except Exception as exc:
            db.session.rollback()
            fail_instance(instance, f"recréation sur {target.hostname} impossible ({exc})")
            continue

        instance.container_id = container_id
        instance.port = port
        instance.status = "RUNNING"
        db.session.commit()
        log.warning("FAILOVER : %s migrée de %s vers %s (nouveau conteneur %s).",
                    instance.name, old_hostname, target.hostname, container_id[:12])


# ---------------------------------------------------------------------------
# 3. Conteneurs : détection de crash et réparation
# ---------------------------------------------------------------------------

def repair_instance(instance, client):
    container_id = instance.container_id
    try:
        container = client.containers.get(container_id)
    except NotFound:
        fail_instance(instance, "conteneur introuvable sur son Worker")
        return

    state = container.attrs.get("State", {})
    status = container.status
    health = state.get("Health", {}).get("Status")

    if status == "running" and health != "unhealthy":
        if is_stable(state):
            restart_counts.pop(container_id, None)
        return

    # created / paused / restarting : on laisse faire
    if not (status in ("exited", "dead") or health == "unhealthy"):
        return

    attempts = restart_counts.get(container_id, 0) + 1
    if attempts > MAX_RESTARTS:
        fail_instance(instance, f"irrécupérable après {MAX_RESTARTS} relances")
        return

    restart_counts[container_id] = attempts
    log.warning("%s : plantage détecté (statut=%s, santé=%s). Relance %d/%d...",
                instance.name, status, health, attempts, MAX_RESTARTS)
    container.restart(timeout=5)
    container.reload()
    port = host_port(container)
    if port and port != instance.port:
        # Le port publié est tiré au sort par Docker à chaque démarrage
        log.info("%s : relancé, nouveau port %s (ancien %s).", instance.name, port, instance.port)
        instance.port = port
        db.session.commit()
    else:
        log.info("%s : relancé.", instance.name)


def check_containers():
    instances = (
        Instance.query.join(Rental).join(Worker)
        .filter(
            Instance.status == "RUNNING",
            Instance.container_id.isnot(None),
            Rental.status == "ACTIVE",
            Rental.end_time > utcnow(),
            Worker.status != "OFFLINE",
        )
        .all()
    )
    clients = {}  # un client SSH par Worker et par cycle
    for instance in instances:
        name, worker_id = instance.name, instance.worker_id
        try:
            if worker_id not in clients:
                clients[worker_id] = provisioner._client(instance.worker)
            repair_instance(instance, clients[worker_id])
        except Exception as exc:
            # Worker injoignable en SSH ou erreur Docker : on ne déclare JAMAIS une instance
            # morte sur cette base, on réessaie au prochain cycle.
            db.session.rollback()
            clients.pop(worker_id, None)
            log.warning("%s : vérification impossible (%s: %s). Nouvel essai au prochain cycle.",
                        name, type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# Boucle principale et /health
# ---------------------------------------------------------------------------

def run_cycle():
    ok = True
    steps = (("workers", check_workers), ("failover", recover_orphans), ("conteneurs", check_containers))
    for label, step in steps:
        try:
            step()
        except Exception:
            db.session.rollback()
            log.exception("Étape '%s' en erreur.", label)
            ok = False
    db.session.remove()
    return ok


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        last_ok = health_state["last_ok"]
        age = None if last_ok is None else round(time.time() - last_ok, 1)
        healthy = age is not None and age < INTERVAL * 3 + 5
        body = json.dumps({"status": "healthy" if healthy else "unhealthy",
                           "seconds_since_last_ok": age}).encode()
        self.send_response(200 if healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # pas de log HTTP à chaque appel


def main():
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app = create_app()
    log.info("Démarrage : cycle %ss, timeout heartbeat %ss, %d relances max, mode Docker : %s.",
             INTERVAL, HEARTBEAT_TIMEOUT, MAX_RESTARTS, os.environ.get("DOCKER_MODE", "remote"))

    with app.app_context():
        while not stop_event.is_set():
            if run_cycle():
                health_state["last_ok"] = time.time()
            stop_event.wait(INTERVAL)

    server.shutdown()
    log.info("Watcher arrêté proprement.")


if __name__ == "__main__":
    main()