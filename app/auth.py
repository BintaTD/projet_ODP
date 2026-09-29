from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from .models import db, User

auth = Blueprint('auth', __name__)

@auth.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Veuillez fournir un identifiant (username) et un mot de passe.'}), 400
        
    # Vérifier si l'utilisateur existe déjà
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': 'Cet identifiant est déjà pris.'}), 400
        
    # Création du nouvel utilisateur avec mot de passe haché (US04)
    new_user = User(
        username=data['username'],
        password_hash=generate_password_hash(data['password'], method='pbkdf2:sha256')
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'message': 'Compte créé avec succès !'}), 201

@auth.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Veuillez fournir un identifiant et un mot de passe.'}), 400
        
    user = User.query.filter_by(username=data['username']).first()
    
    # Vérification du mot de passe
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({'message': 'Identifiant ou mot de passe incorrect.'}), 401
        
    # Connecter l'utilisateur (gère la session)
    login_user(user)
    return jsonify({'message': 'Connexion réussie !', 'username': user.username}), 200

@auth.route('/logout', methods=['POST'])
@login_required # Cette route est protégée, il faut être connecté
def logout():
    logout_user()
    return jsonify({'message': 'Déconnexion réussie !'}), 200
