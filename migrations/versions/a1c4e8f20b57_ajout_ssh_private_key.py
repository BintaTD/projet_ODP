"""Ajout de la clé SSH privée sur les instances

Revision ID: a1c4e8f20b57
Revises: d7919a67506a
Create Date: 2026-10-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4e8f20b57'
down_revision = 'd7919a67506a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('instances', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ssh_private_key', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('instances', schema=None) as batch_op:
        batch_op.drop_column('ssh_private_key')
