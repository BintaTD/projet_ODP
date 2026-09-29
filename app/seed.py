import click
from flask.cli import with_appcontext
from .models import db, Distribution

DISTRIBUTIONS = [
    {
        'name': 'Kali Linux',
        'image_tag': 'kalilinux/kali-rolling',
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
    added = 0
    for data in DISTRIBUTIONS:
        if not Distribution.query.filter_by(name=data['name']).first():
            db.session.add(Distribution(**data))
            added += 1
    db.session.commit()
    click.echo(f'{added} distribution(s) ajoutée(s).')
