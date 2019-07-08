import json
import logging
import os
import signal
import threading
import time

import click
import koji
from sqlalchemy.orm import sessionmaker
from twisted.internet import reactor

from .bodhi_query import refresh_update_status, reset_update_cache
from .db import get_engine
from .distgit import DistGit
from .messaging import MessagePump
from .release_info import releases
from .update import Investigation, UpdateJsonEncoder, Updater

logger = logging.getLogger(__name__)


@click.group()
@click.pass_context
@click.option('--cache-dir', required=True,
              help='Directory for caching data')
@click.option('-v', '--verbose', is_flag=True,
              help='Show verbose debugging output')
def cli(ctx, cache_dir, verbose):
    ctx.obj = {
        'cache_dir': cache_dir,
    }

    if verbose:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger('flatpak_status').setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)


class GlobalObjects:
    def __init__(self, cache_dir, mirror_existing=True):
        engine = get_engine(cache_dir)
        self.session_constructor = sessionmaker(bind=engine)

        options = koji.read_config(profile_name='koji', user_config=None)
        session_opts = koji.grab_session_options(options)
        self.koji_session = koji.ClientSession(options['server'], session_opts)

        self.distgit = DistGit(base_url='https://src.fedoraproject.org',
                               mirror_dir=os.path.join(cache_dir, 'distgit'),
                               mirror_existing=mirror_existing)

    def make_updater(self):
        return Updater(self.session_constructor(),
                       self.koji_session,
                       self.distgit,
                       releases)


def do_update(global_objects, output):
    updater = global_objects.make_updater()

    try:
        investigation = Investigation()
        investigation.investigate(updater)
        updater.db_session.commit()

        with open(output, 'w') as f:
            json.dump(investigation, f, cls=UpdateJsonEncoder, indent=4)

        logger.info("Successfully created json cache at %s", output)
    except Exception:
        updater.db_session.rollback()
        raise
    finally:
        updater.db_session.close()


@click.option('-o', '--output', required=True,
              help='Output filename')
@click.option('--mirror-existing/--no-mirror-existing', is_flag=True, default=True,
              help="Updating mirrors of distgit repos that already existing locally")
@cli.command(name="update")
@click.pass_context
def update(ctx, output, mirror_existing):
    """Regenerate status.json"""

    global_objects = GlobalObjects(ctx.obj['cache_dir'],
                                   mirror_existing=mirror_existing)
    do_update(global_objects, output)


class WorkThread(threading.Thread):
    def __init__(self, cache_dir, output, update_interval):
        super().__init__()

        self.global_objects = GlobalObjects(cache_dir, mirror_existing=False)
        self.output = output
        self.update_interval = update_interval

        self.condition = threading.Condition()
        self.mirror_paths = {}
        self.updated_updates = set()
        self.should_reset_update_cache = False

    def mirror(self, path, rev):
        with self.condition:
            self.mirror_paths[path] = rev
            self.condition.notify()

    def mirror_all(self):
        with self.condition:
            self.mirror_paths['ALL'] = None
            self.condition.notify()

    def reset_update_cache(self):
        with self.condition:
            self.should_reset_update_cache = True
            self.condition.notify()

    def update_update(self, bodhi_update_id):
        with self.condition:
            self.updated_updates.add(bodhi_update_id)
            self.condition.notify()

    def run(self):
        now = time.time()
        next_update_time = now
        while True:
            with self.condition:
                while not self.mirror_paths and \
                      not self.should_reset_update_cache and \
                      not self.updated_updates and \
                      now < next_update_time:
                    self.condition.wait(next_update_time - now)
                    now = time.time()

                mirror_paths = self.mirror_paths
                self.mirror_paths = {}
                should_reset_update_cache = self.should_reset_update_cache
                self.should_reset_update_cache = False
                updated_updates = self.updated_updates
                self.updated_updates = set()

            try:
                if 'ALL' in mirror_paths:
                    logger.info("Updating all git mirrors")
                    self.global_objects.distgit.mirror_all()
                else:
                    for path, rev in mirror_paths.items():
                        repo = self.global_objects.distgit.repo(path)
                        if repo.exists():
                            logger.info("Updating git mirror %s", path)
                            repo.mirror(mirror_always=True)
                            if not repo.verify_rev(rev):
                                logger.warning("Fetch failed to get new rev %s", rev)
            except Exception:
                logger.exception("Error git mirroring")

            if should_reset_update_cache:
                updater = self.global_objects.make_updater()

                try:
                    reset_update_cache(updater.db_session)
                except Exception:
                    logger.exception("Error restting Bodhi update cache")
                    updater.db_session.rollback()
                    raise
                finally:
                    updater.db_session.close()
            elif updated_updates:
                updater = self.global_objects.make_updater()

                try:
                    for bodhi_update_id in updated_updates:
                        refresh_update_status(updater.koji_session,
                                              updater.db_session,
                                              bodhi_update_id)
                    updater.db_session.commit()
                except Exception:
                    logger.exception("Error updating Bodhi updates")
                    updater.db_session.rollback()
                    raise
                finally:
                    updater.db_session.close()

            if now >= next_update_time:
                try:
                    do_update(self.global_objects, self.output)
                except Exception:
                    logger.exception("Error creating new json cache")
                next_update_time = now + self.update_interval


class IdleStarter:
    """Delay starting the workthread until no messages have been received for 1 second."""

    def __init__(self, to_start):
        self.to_start = to_start
        self.started = False
        self.task = None

    def _do_start(self):
        logger.info("Starting after 1 second of idle")
        self.to_start.start()
        self.started = True

    def start_soon(self):
        if not self.started:
            if self.task:
                self.task.cancel()
            self.task = reactor.callLater(1, self._do_start)


@click.option('-o', '--output', required=True,
              help='Output filename')
@click.option('--fedora-messaging-config', required=True,
              help="Path to fedora-messaging config file")
@click.option('--update-interval', type=int, default=1800,
              help="Update interval in seconds (default=1800)")
@cli.command(name="daemon")
@click.pass_context
def daemon(ctx, output, fedora_messaging_config, update_interval):
    # With KeyboardInterrupt handling, the main thread won't exit until
    # the thread dies, but the thread won't die unless some subprocess
    # caught the SIGINT and caused a traceback... It's better to just exit.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    work_thread = WorkThread(ctx.obj['cache_dir'], output, update_interval)
    starter = IdleStarter(work_thread)

    routing_keys = [
        "org.fedoraproject.prod.git.receive",
        "org.fedoraproject.prod.bodhi.update.complete.#",
        "org.fedoraproject.prod.bodhi.update.request.#",
    ]

    message_pump = MessagePump(cache_dir=ctx.obj['cache_dir'],
                               fedora_messaging_config=fedora_messaging_config,
                               routing_keys=routing_keys)

    def on_connected(new_queue):
        logger.info("Connected, new_queue=%s", new_queue)
        if new_queue:
            work_thread.mirror_all()
            # We count on messages to catch certain changes to the status of updates
            # (e.g., when an update is obsolete). So, if we can't reconnect, we start
            # over from scratch. We could just refresh the status of all cached updates,
            # but it would be common that when our queue has been deleted, we've *also*
            # been disconnected for more than bodhi_query.ALL_UPDATES_MAX_INTERVAL -
            # and then refreshing the update status would be doing twice the work.
            work_thread.reset_update_cache()
        starter.start_soon()

    message_pump.on_connected = on_connected

    def on_message(message):
        logger.info("received message for topic %s", message.topic)
        if message.topic == 'org.fedoraproject.prod.git.receive':
            body = message.body
            rev = body['commit']['rev']
            path = body['commit']['namespace'] + '/' + body['commit']['repo']
            logger.info("Saw commit on %s", path)
            work_thread.mirror(path, rev)
        elif (message.topic.startswith('org.fedoraproject.prod.bodhi.update.complete.') or
              message.topic.startswith('org.fedoraproject.prod.bodhi.update.request.')):
            body = message.body
            logger.info("Update %s potentially changed status", body['update']['alias'])
            work_thread.update_update(body['update']['alias'])

        starter.start_soon()

    message_pump.on_message = on_message
    message_pump.run()

    # Only returns on abnormal exit
    os._exit(1)
