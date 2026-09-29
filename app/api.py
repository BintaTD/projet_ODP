import secrets
from datetime import timedelta
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from .models import db, utcnow, Distribution, Worker, Rental, Instance

api = Blueprint('api', __name__)

# Limites autorisées pour une location (US32 : validation de la demande)
CPU_MIN, CPU_MAX = 0.5, 4
RAM_MIN_MB, RAM_MAX_MB = 256, 8192
DURATION_MIN, DURATION_MAX = 5, 480  # en minutes

# Une instance dans un de ces états occupe encore des ressources
ACTIVE_STATUSES = ('PENDING', 'RUNNING')


def iso(dt):
    # Les dates sont stockées en UTC : le 'Z' permet au navigateur de les convertir en heure locale
    return dt.isoformat() + 'Z' if dt else None


def instance_to_dict(instance):
    return {
        'id': instance.id,
        'name': instance.name,
        'container_id': instance.container_id,
        'status': instance.status,
        'distribution': instance.distribution.name,
        'worker': instance.worker.hostname,
        'cpu_limit': instance.cpu_limit,
        'ram_limit_mb': instance.ram_limit_mb,
        'start_time': iso(instance.rental.start_time),
        'end_time': iso(instance.rental.end_time),
        'access_url': None,  # Sera rempli quand Traefik sera en place
    }


def worker_to_dict(worker):
    return {
        'id': worker.id,
        'hostname': worker.hostname,
        'ip_address': worker.ip_address,
        'cpu_cores': worker.cpu_cores,
        'ram_mb': worker.ram_mb,
        'status': worker.status,
        'last_heartbeat': iso(worker.last_heartbeat),
    }


# ---------------------------------------------------------------------------
# Distributions et instances (côté utilisateur)
# ---------------------------------------------------------------------------

@api.route('/distributions', methods=['GET'])
@login_required
def list_distributions():
    distributions = Distribution.query.order_by(Distribution.name).all()
    return jsonify([
        {'id': d.id, 'name': d.name, 'description': d.description}
        for d in distributions
    ])


@api.route('/instances', methods=['GET'])
@login_required
def list_instances():
    # Uniquement les instances de l'utilisateur connecté (isolation, US56)
    instances = (
        Instance.query
        .join(Rental)
        .filter(Rental.user_id == current_user.id)
        .order_by(Rental.start_time.desc())
        .all()
    )
    return jsonify([instance_to_dict(i) for i in instances])


@api.route('/rent', methods=['POST'])
@login_required
def rent():
    data = request.get_json(silent=True) or {}

    # 1. Validation des champs
    try:
        distribution_id = int(data['distribution_id'])
        cpu = float(data['cpu'])
        ram_mb = int(data['ram_mb'])
        duration = int(data['duration_minutes'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'message': 'Champs requis : distribution_id, cpu, ram_mb, duration_minutes.'}), 400

    if not CPU_MIN <= cpu <= CPU_MAX:
        return jsonify({'message': f'Le CPU doit être entre {CPU_MIN} et {CPU_MAX}.'}), 400
    if not RAM_MIN_MB <= ram_mb <= RAM_MAX_MB:
        return jsonify({'message': f'La RAM doit être entre {RAM_MIN_MB} et {RAM_MAX_MB} Mo.'}), 400
    if not DURATION_MIN <= duration <= DURATION_MAX:
        return jsonify({'message': f'La durée doit être entre {DURATION_MIN} et {DURATION_MAX} minutes.'}), 400

    distribution = db.session.get(Distribution, distribution_id)
    if not distribution:
        return jsonify({'message': 'Distribution inconnue.'}), 404

    # 2. Règle du projet : 1 utilisateur = 1 conteneur actif
    already_active = (
        Instance.query
        .join(Rental)
        .filter(Rental.user_id == current_user.id, Instance.status.in_(ACTIVE_STATUSES))
        .first()
    )
    if already_active:
        return jsonify({'message': 'Vous avez déjà une instance active. Arrêtez-la avant d\'en louer une autre.'}), 409

    # 3. Choix du Worker : version simple, le Resource Manager (US27-US29) viendra plus tard
    worker = Worker.query.filter_by(status='AVAILABLE').order_by(Worker.id).first()
    if not worker:
        return jsonify({'message': 'Aucun Worker disponible pour le moment.'}), 503

    # 4. Enregistrement en base : User -> Rental -> Instance -> Worker (US33)
    now = utcnow()
    rental = Rental(user_id=current_user.id, start_time=now, end_time=now + timedelta(minutes=duration))
    instance = Instance(
        name=f'lab-{current_user.id}-{secrets.token_hex(4)}',  # Nom unique, utilisable par Traefik
        rental=rental,
        worker=worker,
        distribution=distribution,
        cpu_limit=cpu,
        ram_limit_mb=ram_mb,
        status='PENDING',  # Le conteneur Docker n'existe pas encore
    )
    db.session.add_all([rental, instance])
    db.session.commit()

    # --- TEST LOCAL uniquement, ne pas pousser ---
    import docker
    client = docker.from_env()
    network = client.networks.create(f"net-user-{current_user.id}-{instance.id}", driver="bridge")
    host_port = 2300 + instance.id

    container = client.containers.run(
        image="pentest-image",
        name=instance.name,
        network=network.name,
        ports={"22/tcp": host_port},
        environment={"SSH_PUBLIC_KEY": open("/Users/macbookair/Desktop/projet_ODP/docker/test_key.pub").read().strip()},
        mem_limit=f"{instance.ram_limit_mb}m",
        nano_cpus=int(instance.cpu_limit * 1_000_000_000),
        cap_drop=["ALL"],
        cap_add=["SYS_CHROOT", "SETGID", "SETUID", "CHOWN", "AUDIT_WRITE"],
        read_only=True,
        tmpfs={"/home/pentest/.ssh": "mode=755", "/run": ""},
        detach=True,
    )

    instance.status = 'RUNNING'
    instance.container_id = container.id
    instance.port = host_port
    db.session.commit()
    # --- fin test local ---

    return jsonify(instance_to_dict(instance)), 201


@api.route('/instances/<int:instance_id>/stop', methods=['POST'])
@login_required
def stop_instance(instance_id):
    instance = db.session.get(Instance, instance_id)

    # 404 aussi si l'instance appartient à un autre utilisateur : on ne révèle pas qu'elle existe
    if not instance or instance.rental.user_id != current_user.id:
        return jsonify({'message': 'Instance introuvable.'}), 404
    if instance.status not in ACTIVE_STATUSES:
        return jsonify({'message': 'Cette instance est déjà arrêtée.'}), 409

    instance.status = 'STOPPED'
    instance.rental.status = 'ENDED'
    db.session.commit()

    return jsonify(instance_to_dict(instance)), 200


# ---------------------------------------------------------------------------
# Workers (appelés par le Worker Agent, FONCTIONNALITÉ 07)
# ---------------------------------------------------------------------------

@api.route('/workers', methods=['GET'])
@login_required
def list_workers():
    workers = Worker.query.order_by(Worker.hostname).all()
    return jsonify([worker_to_dict(w) for w in workers])


@api.route('/workers/register', methods=['POST'])
def register_worker():
    data = request.get_json(silent=True) or {}

    try:
        hostname = str(data['hostname']).strip()
        ip_address = str(data['ip_address']).strip()
        cpu_cores = int(data['cpu_cores'])
        ram_mb = int(data['ram_mb'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'message': 'Champs requis : hostname, ip_address, cpu_cores, ram_mb.'}), 400

    if not hostname or not ip_address or cpu_cores <= 0 or ram_mb <= 0:
        return jsonify({'message': 'Valeurs invalides.'}), 400

    # Un Worker qui redémarre se ré-enregistre : on met à jour au lieu de créer un doublon
    worker = Worker.query.filter_by(hostname=hostname).first()
    created = worker is None
    if created:
        worker = Worker(hostname=hostname)
        db.session.add(worker)

    worker.ip_address = ip_address
    worker.cpu_cores = cpu_cores
    worker.ram_mb = ram_mb
    worker.status = 'AVAILABLE'
    worker.last_heartbeat = utcnow()
    db.session.commit()

    return jsonify(worker_to_dict(worker)), 201 if created else 200


@api.route('/workers/heartbeat', methods=['POST'])
def worker_heartbeat():
    data = request.get_json(silent=True) or {}
    hostname = str(data.get('hostname', '')).strip()
    if not hostname:
        return jsonify({'message': 'Champ requis : hostname.'}), 400

    worker = Worker.query.filter_by(hostname=hostname).first()
    if not worker:
        return jsonify({'message': 'Worker inconnu, appelez /workers/register d\'abord.'}), 404

    worker.last_heartbeat = utcnow()
    if worker.status == 'OFFLINE':
        worker.status = 'AVAILABLE'  # Le Worker est revenu
    db.session.commit()

    return jsonify(worker_to_dict(worker)), 200
