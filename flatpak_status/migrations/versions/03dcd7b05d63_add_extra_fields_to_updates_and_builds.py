"""Add extra fields to updates and builds

Revision ID: 03dcd7b05d63
Revises: 8e089a7d484f
Create Date: 2019-02-25 18:23:11.685427+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '03dcd7b05d63'
down_revision = '8e089a7d484f'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('DELETE from flatpak_update_builds')
    op.execute('DELETE from flatpak_updates')
    op.execute('DELETE from package_update_builds')
    op.execute('DELETE from package_updates')
    op.execute('DELETE from flatpak_build_package_builds')
    op.execute('DELETE from flatpak_build_module_builds')
    op.execute('DELETE from flatpak_builds')
    op.execute('DELETE from module_build_package_builds')
    op.execute('DELETE from module_builds')
    op.execute('DELETE from package_builds')
    op.execute('DELETE from update_cache_items')
    op.execute('DELETE from build_cache_items')

    with op.batch_alter_table('flatpak_builds', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('user_name', sa.String(), nullable=False))
    with op.batch_alter_table('module_builds', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('user_name', sa.String(), nullable=False))
    with op.batch_alter_table('package_builds', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('user_name', sa.String(), nullable=False))

    with op.batch_alter_table('flatpak_updates', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('date_submitted', sa.DateTime(), nullable=False))
        batch_op.add_column(sa.Column('user_name', sa.String(), nullable=False))
    with op.batch_alter_table('package_updates', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('date_submitted', sa.DateTime(), nullable=False))
        batch_op.add_column(sa.Column('user_name', sa.String(), nullable=False))


def downgrade():
    # This doesn't actually work - as of sqlalchemy-1.2.18, the batch_alter_table
    # support for drop_column seems broken.
    #
    with op.batch_alter_table('flatpak_builds') as batch_op:
        batch_op.drop_column(sa.Column('user_name'))
    with op.batch_alter_table('module_builds') as batch_op:
        batch_op.drop_column(sa.Column('user_name'))
    with op.batch_alter_table('package_builds') as batch_op:
        batch_op.drop_column(sa.Column('user_name'))

    with op.batch_alter_table('flatpak_updates') as batch_op:
        batch_op.drop_column(sa.Column('date_submitted'))
        batch_op.drop_column(sa.Column('user_name'))
    with op.batch_alter_table('package_updates') as batch_op:
        batch_op.drop_column(sa.Column('date_submitted'))
        batch_op.drop_column(sa.Column('user_name'))
