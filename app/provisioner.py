"""Création / suppression des conteneurs pentest sur un Worker (US35-US38).

Le contrôleur pilote le Docker du Worker via le SDK Docker Python, à travers SSH.
DOCKER_MODE=local : utilise le Docker de la machine courante (tests sans les VM).
"""
import os

import docker

SSH_USER = os.environ.get('WORKER_SSH_USER', 'vagrant')
PENTEST_IMAGE = os.environ.get('PENTEST_IMAGE', 'pentest-image')


def _client(worker):
    if os.environ.get('DOCKER_MODE') == 'local':
        return docker.from_env()
    return docker.DockerClient(base_url=f'ssh://{SSH_USER}@{worker.ip_address}', use_ssh_client=True)


def _network_name(instance):
    return f'net-{instance.name}'   # un réseau dédié par instance = isolation entre utilisateurs


def create_container(instance):
    """Crée et démarre le conteneur. Retourne (container_id, port_hôte du terminal web)."""
    client = _client(instance.worker)
    network = client.networks.create(_network_name(instance), driver='bridge')
    try:
        container = client.containers.run(
            image=PENTEST_IMAGE,
            name=instance.name,
            network=network.name,
            ports={'7681/tcp': None},            # port hôte choisi par Docker
            mem_limit=f'{instance.ram_limit_mb}m',
            nano_cpus=int(instance.cpu_limit * 1_000_000_000),
            cap_drop=['ALL'],                    # ttyd/bash n'ont besoin d'aucune capability
            security_opt=['no-new-privileges'],
            pids_limit=256,
            read_only=True,
            tmpfs={'/home/pentest': 'uid=1000,gid=1000,mode=755,size=64m', '/tmp': 'size=64m'},
            detach=True,
        )
        container.reload()
        host_port = int(container.attrs['NetworkSettings']['Ports']['7681/tcp'][0]['HostPort'])
    except Exception:
        network.remove()                         # pas de réseau orphelin si le conteneur échoue
        raise
    return container.id, host_port


def remove_container(instance):
    """Arrête et supprime le conteneur puis son réseau (déjà absent = pas d'erreur)."""
    if not instance.container_id:
        return   # jamais créé (ex. instance restée PENDING) : rien à supprimer sur le worker
    client = _client(instance.worker)
    if instance.container_id:
        try:
            container = client.containers.get(instance.container_id)
            container.stop(timeout=5)
            container.remove()
        except docker.errors.NotFound:
            pass
    try:
        client.networks.get(_network_name(instance)).remove()
    except docker.errors.NotFound:
        pass
