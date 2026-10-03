import click
from flask.cli import with_appcontext
from .models import db, Distribution

DISTRIBUTIONS = [
    {
        'name': 'Kali Linux',
        'image_tag': 'pentest-kali',
        'description': 'Distribution de référence pour le pentest (Offensive Security).',
    },
    {
        'name': 'Parrot Security',
        'image_tag': 'parrotsec/security',
        'description': 'Distribution orientée sécurité et forensique, plus légère que Kali.',
    },
    {
        'name': 'Pentest Debian',
        'image_tag': 'pentest-image',
        'description': 'Image de test locale, basée sur Debian, durcie (SSH, isolation, capacités).',
    },
]


@click.command('seed')
@with_appcontext
def seed_command():
    """Ajoute les distributions de base (ne crée pas de doublons)."""
    added = updated = 0
    for data in DISTRIBUTIONS:
        dist = Distribution.query.filter_by(name=data['name']).first()
        if not dist:
            db.session.add(Distribution(**data))
            added += 1
        elif dist.image_tag != data['image_tag']:
            dist.image_tag = data['image_tag']  # corrige les bases déjà seedées
            updated += 1
    db.session.commit()
    click.echo(f'{added} distribution(s) ajoutée(s), {updated} mise(s) à jour.')
