import os
from flask import Flask, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from .models import db

load_dotenv()  # Charge les variables du fichier .env

migrate = Migrate()

def create_app():
    app = Flask(__name__)
    
    # Configuration de la base de données depuis les variables d'environnement
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///dev.db').replace('postgresql://', 'postgresql+psycopg://')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-default')
    
    # Initialisation des extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Configuration de l'authentification (Flask-Login)
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.login_view = 'main.index'  # Page HTML de connexion (GET /)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        # Les routes API répondent en JSON, les pages HTML redirigent vers le login
        if request.blueprint in ('api', 'auth'):
            return jsonify({'message': 'Authentification requise.'}), 401
        return redirect(url_for(login_manager.login_view, next=request.path))

    # Enregistrement des routes d'authentification (API)
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)
    
    # Enregistrement des pages frontend (HTML)
    from .views import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Enregistrement des routes API métier (instances, location, workers)
    from .api import api as api_blueprint
    app.register_blueprint(api_blueprint)

    # Commande `flask seed` : remplit le catalogue des distributions
    from .seed import seed_command
    app.cli.add_command(seed_command)
    
    @app.route('/health')
    def health():
        return {'status': 'healthy'}
        
    return app

