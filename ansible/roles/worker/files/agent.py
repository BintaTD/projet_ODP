#!/usr/bin/env python3
"""
agent.py - ODP Worker Agent (US23-US26)
Envoie un heartbeat toutes les 10 secondes au Controller pour prouver que le Worker est en vie.
"""
import os
import time
import socket
import logging
import requests
import psutil

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# L'IP du Controller (passée par systemd/Ansible)
CONTROLLER_URL = os.environ.get("CONTROLLER_URL", "http://192.168.56.10")
HEARTBEAT_INTERVAL = 10

def get_system_info():
    return {
        "hostname": socket.gethostname(),
        "ip_address": socket.gethostbyname(socket.gethostname()),
        "cpu_cores": psutil.cpu_count(logical=True),
        "ram_mb": int(psutil.virtual_memory().total / (1024 * 1024))
    }

def register_worker(info):
    url = f"{CONTROLLER_URL}/workers/register"
    try:
        response = requests.post(url, json=info, timeout=5)
        response.raise_for_status()
        logging.info(f"Enregistrement réussi : {response.status_code}")
        return True
    except requests.RequestException as e:
        logging.error(f"Échec de l'enregistrement : {e}")
        return False

def send_heartbeat(hostname):
    url = f"{CONTROLLER_URL}/workers/heartbeat"
    try:
        requests.post(url, json={"hostname": hostname}, timeout=5)
        logging.info("Heartbeat envoyé.")
    except requests.RequestException as e:
        logging.error(f"Échec du heartbeat : {e}")

def main():
    info = get_system_info()
    logging.info(f"Démarrage de l'agent pour le worker {info['hostname']}...")

    # On s'assure d'être enregistré au démarrage
    while not register_worker(info):
        logging.info("Nouvelle tentative d'enregistrement dans 5s...")
        time.sleep(5)

    # Boucle infinie du heartbeat
    while True:
        send_heartbeat(info["hostname"])
        time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    main()