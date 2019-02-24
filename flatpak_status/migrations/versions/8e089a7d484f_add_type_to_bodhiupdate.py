"""Add type to BodhiUpdate

Revision ID: 8e089a7d484f
Revises:
Create Date: 2019-02-23 05:34:54.773990+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8e089a7d484f'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('flatpak_updates', sa.Column('type', sa.String(),
                                               nullable=False, server_default='bugfix'))
    op.add_column('package_updates', sa.Column('type', sa.String(),
                                               nullable=False, server_default='bugfix'))
    op.execute('DELETE from flatpak_updates')
    op.execute('DELETE from flatpak_update_builds')
    op.execute('DELETE from package_updates')
    op.execute('DELETE from package_update_builds')
    op.execute('DELETE from update_cache_items')


def downgrade():
    op.drop_column('package_updates', 'type')
    op.drop_column('flatpak_updates', 'type')
