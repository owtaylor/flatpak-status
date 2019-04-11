import json
import logging
import os
import signal
import threading
import time

import click
import fedmsg
import koji
from sqlalchemy.orm import sessionmaker

from .db import get_engine
from .distgit import DistGit
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
        logging.basicConfig(level=logging.INFO)
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

    def mirror(self, path, rev):
        with self.condition:
            self.mirror_paths[path] = rev
            self.condition.notify()

    def mirror_all(self):
        with self.condition:
            self.mirror_paths['ALL'] = None
            self.condition.notify()

    def run(self):
        now = time.time()
        next_update_time = now
        while True:
            with self.condition:
                while not self.mirror_paths and now < next_update_time:
                    self.condition.wait(next_update_time - now)
                    now = time.time()

                mirror_paths = self.mirror_paths
                self.mirror_paths = {}

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

            if now >= next_update_time:
                try:
                    do_update(self.global_objects, self.output)
                except Exception:
                    logger.exception("Error creating new json cache")
                next_update_time = now + self.update_interval


def _suppress_fedmsg_routing_warnings():
    # fedmsg's routing policy mechanism is meant to allow binding particular
    # messages to the crypto certificates for particular servers in the
    # infrastructure. Setting this up outside of Fedora infrastructure would
    # be difficult, so we just filter out the nag messages that occur when
    # no routing policy is set, but messages aren't actually blocked.

    class NoRoutingFilter(logging.Filter):
        def filter(self, record):
            return not (record.msg.startswith("No routing policy defined") and
                        "but routing_nitpicky is False" in record.msg)

    logging.getLogger('fedmsg.crypto.utils').addFilter(NoRoutingFilter())


@click.option('-o', '--output', required=True,
              help='Output filename')
@click.option('--mirror-existing/--no-mirror-existing', is_flag=True, default=True,
              help="Initially update all existing distgit repos (default)")
@click.option('--update-interval', type=int, default=1800,
              help="Update interval in seconds (default=1800)")
@cli.command(name="daemon")
@click.pass_context
def daemon(ctx, output, mirror_existing, update_interval):
    _suppress_fedmsg_routing_warnings()

    # With KeyboardInterrupt handling, the main thread won't exit until
    # the thread dies, but the thread won't die unless some subprocess
    # caught the SIGINT and caused a traceback... It's better to just exit.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    work_thread = WorkThread(ctx.obj['cache_dir'], output, update_interval)
    if mirror_existing:
        work_thread.mirror_all()
    work_thread.start()

    fedmsg.init(mute=True)
    match_topic = 'org.fedoraproject.prod.git.receive'
    for name, endpoint, topic, raw_msg in fedmsg.tail_messages(topic=match_topic):
        msg = raw_msg['msg']
        rev = msg['commit']['rev']
        path = msg['commit']['namespace'] + '/' + msg['commit']['repo']
        logger.info("Saw commit on %s", path)
        work_thread.mirror(path, rev)
