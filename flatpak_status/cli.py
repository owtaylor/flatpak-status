import json
import logging
import os
import threading
import time

import click
import fedmsg
import koji
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .distgit import DistGit
from .models import Base
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
        db_file = os.path.join(cache_dir, 'status.db')
        existed = os.path.exists(db_file)

        engine = create_engine('sqlite:///' + db_file, echo=False)
        if not existed:
            Base.metadata.create_all(engine)

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
                       self.distgit)


def do_update(global_objects, output):
    investigation = Investigation()
    investigation.add_flatpak('0ad')
    investigation.add_flatpak('eog')
    investigation.add_flatpak('feedreader')
    investigation.add_flatpak('flatpak-runtime')
    investigation.add_flatpak('gnome-clocks')
    investigation.add_flatpak('quadrapassel')
    investigation.add_flatpak('wesnoth')

    updater = global_objects.make_updater()
    investigation.investigate(updater)
    updater.db_session.commit()

    with open(output, 'w') as f:
        json.dump(investigation, f, cls=UpdateJsonEncoder, indent=4)


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
                            repo.update()
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


@click.option('-o', '--output', required=True,
              help='Output filename')
@click.option('--mirror-all/--no-mirror-all', is_flag=True, default=True,
              help="Initially update all existing distgit repos (default)")
@click.option('--update-interval', type=int, default=1800,
              help="Update interval in seconds (default=1800)")
@cli.command(name="daemon")
@click.pass_context
def daemon(ctx, output, mirror_all, update_interval):

    work_thread = WorkThread(ctx.obj['cache_dir'], output, update_interval)
    if mirror_all:
        work_thread.mirror_all()
    work_thread.start()

    fedmsg.init(mute=True)
    match_topic = 'org.fedoraproject.prod.git.receive'
    for name, endpoint, topic, raw_msg in fedmsg.tail_messages(topic=match_topic):
        msg = raw_msg['msg']
        print(name, endpoint, topic, msg)
        print(msg['commit'])
        print(msg['commit']['namespace'])
        print(msg['commit']['repo'])
        rev = msg['commit']['rev']

        path = msg['commit']['namespace'] + '/' + msg['commit']['repo']
        logger.info("Saw commit on %s", path)
        work_thread.mirror(path, rev)
