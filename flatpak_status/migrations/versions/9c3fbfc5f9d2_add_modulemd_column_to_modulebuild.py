"""Add modulemd column to ModuleBuild

Revision ID: 9c3fbfc5f9d2
Revises: dbd98058e57f
Create Date: 2019-03-15 19:42:59.987965+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c3fbfc5f9d2'
down_revision = 'dbd98058e57f'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('DELETE from flatpak_update_builds')
    op.execute('DELETE from flatpak_updates')
    op.execute('DELETE from flatpak_build_package_builds')
    op.execute('DELETE from flatpak_build_module_builds')
    op.execute('DELETE from flatpak_builds')
    op.execute('DELETE from module_build_package_builds')
    op.execute('DELETE from module_builds')
    op.execute('DELETE from update_cache_items WHERE content_type = "flatpak"')
    op.execute('DELETE from build_cache_items')

    with op.batch_alter_table('module_builds', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('modulemd', sa.String(), nullable=False))


def downgrade():
    with op.batch_alter_table('module_builds', recreate='always') as batch_op:
        batch_op.drop_column('modulemd')
