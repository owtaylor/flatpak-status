from datetime import timedelta
import json
import logging
import os
import signal
import time

import click
from flatpak_indexer import fedora_monitor
from flatpak_indexer.bodhi_query import refresh_update_status, reset_update_cache
from flatpak_indexer.koji_utils import KojiConfig
from flatpak_indexer.redis_utils import RedisConfig

from . import distgit
from .update import Investigation, UpdateJsonEncoder, Updater

logger = logging.getLogger(__name__)


class Config(KojiConfig, RedisConfig):
    cache_dir: str
    output: str
    update_interval: timedelta = timedelta(seconds=1800)


@click.group()
@click.pass_context
@click.option('--config-file', '-c', required=True,
              help='Config file')
@click.option('-v', '--verbose', is_flag=True,
              help='Show verbose debugging output')
def cli(ctx, config_file, verbose):
    cfg = Config.from_path(config_file)

    ctx.obj = {
        'config': cfg,
    }

    if verbose:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger('flatpak_status').setLevel(logging.INFO)
        logging.getLogger('flatpak_indexer').setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)


class GlobalObjects:
    def __init__(self, config, mirror_existing=True):
        self.config = config
        self.distgit = distgit.DistGit(base_url='https://src.fedoraproject.org',
                                       mirror_dir=os.path.join(config.cache_dir, 'distgit'),
                                       mirror_existing=mirror_existing)

    def make_updater(self):
        return Updater(self.config, self.distgit)


def do_update(global_objects):
    updater = global_objects.make_updater()

    investigation = Investigation()
    investigation.investigate(updater)

    with open(global_objects.config.output, 'w') as f:
        json.dump(investigation, f, cls=UpdateJsonEncoder, indent=4)

    logger.info("Successfully created json cache at %s", global_objects.config.output)


@click.option('--mirror-existing/--no-mirror-existing', is_flag=True, default=True,
              help="Updating mirrors of distgit repos that already existing locally")
@cli.command(name="update")
@click.pass_context
def update(ctx, mirror_existing):
    """Regenerate status.json"""

    global_objects = GlobalObjects(ctx.obj['config'],
                                   mirror_existing=mirror_existing)
    do_update(global_objects)


@cli.command(name="daemon")
@click.pass_context
def daemon(ctx):
    # With KeyboardInterrupt handling, the main thread won't exit until
    # the thread dies, but the thread won't die unless some subprocess
    # caught the SIGINT and caused a traceback... It's better to just exit.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    config = ctx.obj['config']
    global_objects = GlobalObjects(config, mirror_existing=False)

    monitor = fedora_monitor.FedoraMonitor(
        config, watch_bodhi_updates=True, watch_distgit_changes=True
    )
    monitor.start()

    now = time.time()
    next_update_time = None
    while True:
        now = time.time()
        if next_update_time is not None:
            wait_time = next_update_time - now
            if wait_time > 0:
                time.sleep(next_update_time - now)
        next_update_time = now + config.update_interval.total_seconds()

        bodhi_changed, serial = monitor.get_bodhi_changed()

        updater = global_objects.make_updater()
        if bodhi_changed is None:
            reset_update_cache(updater.redis_client)
        else:
            for bodhi_update_id in bodhi_changed:
                refresh_update_status(updater.koji_session,
                                      updater.redis_client,
                                      bodhi_update_id)

        monitor.clear_bodhi_changed(serial)

        distgit_changed, serial = monitor.get_distgit_changed()

        if distgit_changed is None:
            global_objects.distgit.mirror_all()
        else:
            for path in distgit_changed:
                repo = global_objects.distgit.repo(path)
                if repo.exists():
                    logger.info("Updating git mirror %s", path)
                    repo.mirror(mirror_always=True)

        monitor.clear_distgit_changed(serial)

        try:
            do_update(global_objects)
        except Exception:
            logger.exception("Failed to update JSON cache")
