from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

def utcnow():
    # Heure UTC sans fuseau (datetime.utcnow est déprécié depuis Python 3.12)
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    
    # Relations: Un utilisateur peut avoir plusieurs locations
    rentals = db.relationship('Rental', backref='user', lazy=True)

class Distribution(db.Model):
    __tablename__ = 'distributions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False) # ex: 'Kali Linux', 'ParrotOS'
    image_tag = db.Column(db.String(120), nullable=False) # ex: 'kalilinux/kali-rolling'
    description = db.Column(db.Text, nullable=True)
    
    instances = db.relationship('Instance', backref='distribution', lazy=True)

class Worker(db.Model):
    __tablename__ = 'workers'
    
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(120), unique=True, nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    cpu_cores = db.Column(db.Integer, nullable=False)
    ram_mb = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default='AVAILABLE') # AVAILABLE, BUSY, OFFLINE
    last_heartbeat = db.Column(db.DateTime, default=utcnow)
    
    instances = db.relationship('Instance', backref='worker', lazy=True)

class Rental(db.Model):
    __tablename__ = 'rentals'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=utcnow)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default='ACTIVE') # ACTIVE, ENDED (arrêt manuel), EXPIRED
    
    # Un Rental est associé à une seule Instance
    instance = db.relationship('Instance', backref='rental', uselist=False, lazy=True)

class Instance(db.Model):
    __tablename__ = 'instances'
    
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.String(120), unique=True, nullable=True) # Remplit quand Docker le crée
    name = db.Column(db.String(120), unique=True, nullable=False) # Nom pour Traefik
    
    rental_id = db.Column(db.Integer, db.ForeignKey('rentals.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('workers.id'), nullable=False)
    distribution_id = db.Column(db.Integer, db.ForeignKey('distributions.id'), nullable=False)
    
    cpu_limit = db.Column(db.Float, nullable=False)
    ram_limit_mb = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default='PENDING') # PENDING, RUNNING, STOPPED, DELETED, ERROR
    port = db.Column(db.Integer, nullable=True)
    ssh_private_key = db.Column(db.Text, nullable=True)  # Générée à la location, effacée à l'arrêt
