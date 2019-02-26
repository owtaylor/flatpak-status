"""mark columns not-null

Revision ID: dbd98058e57f
Revises: 03dcd7b05d63
Create Date: 2019-02-26 04:50:08.261047+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dbd98058e57f'
down_revision = '03dcd7b05d63'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('build_cache_items', recreate='always') as batch_op:
        batch_op.alter_column('last_queried',
                              existing_type=sa.DATETIME(),
                              nullable=False)
    with op.batch_alter_table('flatpak_build_module_builds', recreate='always') as batch_op:
        batch_op.alter_column('flatpak_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.alter_column('module_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
    with op.batch_alter_table('flatpak_build_package_builds', recreate='always') as batch_op:
        batch_op.alter_column('flatpak_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.alter_column('package_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
    with op.batch_alter_table('flatpak_builds', recreate='always') as batch_op:
        batch_op.alter_column('completion_time',
                              existing_type=sa.DATETIME(),
                              nullable=False)
        batch_op.alter_column('entity_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
    with op.batch_alter_table('flatpak_update_builds', recreate='always') as batch_op:
        batch_op.alter_column('update_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
    with op.batch_alter_table('flatpak_updates', recreate='always') as batch_op:
        batch_op.alter_column('bodhi_update_id',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
        batch_op.alter_column('release_branch',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
        batch_op.alter_column('release_name',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
        batch_op.alter_column('status',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
    with op.batch_alter_table('flatpaks', recreate='always') as batch_op:
        batch_op.alter_column('name',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
    with op.batch_alter_table('module_build_package_builds', recreate='always') as batch_op:
        batch_op.alter_column('module_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.alter_column('package_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
    with op.batch_alter_table('module_builds', recreate='always') as batch_op:
        batch_op.alter_column('completion_time',
                              existing_type=sa.DATETIME(),
                              nullable=False)
        batch_op.alter_column('entity_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
    with op.batch_alter_table('modules', recreate='always') as batch_op:
        batch_op.alter_column('name',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
    with op.batch_alter_table('package_builds', recreate='always') as batch_op:
        batch_op.alter_column('completion_time',
                              existing_type=sa.DATETIME(),
                              nullable=False)
        batch_op.alter_column('entity_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
    with op.batch_alter_table('package_update_builds', recreate='always') as batch_op:
        batch_op.alter_column('update_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
    with op.batch_alter_table('package_updates', recreate='always') as batch_op:
        batch_op.alter_column('bodhi_update_id',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
        batch_op.alter_column('release_branch',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
        batch_op.alter_column('release_name',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
        batch_op.alter_column('status',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
    with op.batch_alter_table('packages', recreate='always') as batch_op:
        batch_op.alter_column('name',
                              existing_type=sa.VARCHAR(),
                              nullable=False)
    with op.batch_alter_table('update_cache_items', recreate='always') as batch_op:
        batch_op.alter_column('last_queried',
                              existing_type=sa.DATETIME(),
                              nullable=False)


def downgrade():
    with op.batch_alter_table('build_cache_items', recreate='always') as batch_op:
        batch_op.alter_column('last_queried',
                              existing_type=sa.DATETIME(),
                              nullable=True)
    with op.batch_alter_table('flatpak_build_module_builds', recreate='always') as batch_op:
        batch_op.alter_column('flatpak_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.alter_column('module_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
    with op.batch_alter_table('flatpak_build_package_builds', recreate='always') as batch_op:
        batch_op.alter_column('flatpak_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.alter_column('package_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
    with op.batch_alter_table('flatpak_builds', recreate='always') as batch_op:
        batch_op.alter_column('completion_time',
                              existing_type=sa.DATETIME(),
                              nullable=True)
        batch_op.alter_column('entity_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
    with op.batch_alter_table('flatpak_update_builds', recreate='always') as batch_op:
        batch_op.alter_column('update_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
    with op.batch_alter_table('flatpak_updates', recreate='always') as batch_op:
        batch_op.alter_column('bodhi_update_id',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
        batch_op.alter_column('release_branch',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
        batch_op.alter_column('release_name',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
        batch_op.alter_column('status',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
    with op.batch_alter_table('flatpaks', recreate='always') as batch_op:
        batch_op.alter_column('name',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
    with op.batch_alter_table('module_build_package_builds', recreate='always') as batch_op:
        batch_op.alter_column('module_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.alter_column('package_build_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
    with op.batch_alter_table('module_builds', recreate='always') as batch_op:
        batch_op.alter_column('completion_time',
                              existing_type=sa.DATETIME(),
                              nullable=True)
        batch_op.alter_column('entity_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
    with op.batch_alter_table('modules', recreate='always') as batch_op:
        batch_op.alter_column('name',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
    with op.batch_alter_table('package_builds', recreate='always') as batch_op:
        batch_op.alter_column('completion_time',
                              existing_type=sa.DATETIME(),
                              nullable=True)
        batch_op.alter_column('entity_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
    with op.batch_alter_table('package_update_builds', recreate='always') as batch_op:
        batch_op.alter_column('update_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
    with op.batch_alter_table('package_updates', recreate='always') as batch_op:
        batch_op.alter_column('bodhi_update_id',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
        batch_op.alter_column('release_branch',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
        batch_op.alter_column('release_name',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
        batch_op.alter_column('status',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
    with op.batch_alter_table('packages', recreate='always') as batch_op:
        batch_op.alter_column('name',
                              existing_type=sa.VARCHAR(),
                              nullable=True)
    with op.batch_alter_table('update_cache_items', recreate='always') as batch_op:
        batch_op.alter_column('last_queried',
                              existing_type=sa.DATETIME(),
                              nullable=True)
