import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from .models import Base


def _get_alembic_cfg():
    migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
    alembic_ini_path = os.path.join(migrations_dir, 'alembic.ini')
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option('script_location', migrations_dir)
    alembic_cfg.set_main_option('version_locations', os.path.join(migrations_dir, 'versions'))

    return alembic_cfg


def create_db(engine):
    Base.metadata.create_all(engine)

    alembic_cfg = _get_alembic_cfg()
    with engine.begin() as connection:
        alembic_cfg.attributes['connection'] = connection
        command.stamp(alembic_cfg, "head")


def upgrade_db(engine):
    alembic_cfg = _get_alembic_cfg()
    with engine.begin() as connection:
        alembic_cfg.attributes['connection'] = connection
        command.upgrade(alembic_cfg, "head")


def get_engine(cache_dir):
    db_file = os.path.join(cache_dir, 'status.db')
    existed = os.path.exists(db_file)

    engine = create_engine('sqlite:///' + db_file, echo=False)
    if not existed:
        create_db(engine)
    else:
        upgrade_db(engine)

    return engine
