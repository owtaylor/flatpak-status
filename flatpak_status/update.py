#!/usr/bin/python3

import functools
import json
import logging
from urllib.parse import urlparse

from rpm import labelCompare

from .bodhi_query import list_updates, refresh_all_updates, refresh_updates
from .distgit import OrderingError
from .koji_query import list_flatpak_builds, refresh_flatpak_builds
from .models import Flatpak

logger = logging.getLogger(__name__)


def nvrcmp(nvr_a, nvr_b):
    n_a, v_a, r_a = nvr_a.rsplit('-', 2)
    n_b, v_b, r_b = nvr_b.rsplit('-', 2)

    assert n_a == n_b

    return labelCompare(('0', v_a, r_a),
                        ('0', v_b, r_b))


class Updater:
    def __init__(self, db_session, koji_session, distgit):
        self.db_session = db_session
        self.koji_session = koji_session
        self.distgit = distgit
        self.package_investigation_cache = {}


def _time_to_json(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _build_to_json(build):
    return {
        'id': build.koji_build_id,
        'nvr': build.nvr,
        'user_name': build.user_name,
        'completion_time': _time_to_json(build.completion_time),
    }


def _update_to_json(update):
    return {
        'id': update.bodhi_update_id,
        'status': update.status,
        'type': update.type,
        'user_name': update.user_name,
        'date_submitted': _time_to_json(update.date_submitted),
    }


class PackageBuildInvestigationItem:
    def __init__(self, commit, build, update):
        self.commit = commit
        self.build = build
        self.update = update

    def to_json(self):
        result = {
            'commit': self.commit,
            'build': _build_to_json(self.build),
        }
        if self.update is not None:
            result['update'] = _update_to_json(self.update)

        return result


def _get_commit(build):
    source = build.source
    return urlparse(source).fragment


class PackageBuildInvestigation:
    def __init__(self, build, module_build):
        self.build = build
        self.module_build = module_build
        self.commit = _get_commit(build)
        self.branch = None
        self.items = []

    def investigate(self, updater):
        package = self.build.package
        repo = updater.distgit.repo('rpms/' + package.name)

        commit_branches = repo.get_branches(self.commit)
        if len(commit_branches) > 1:
            self.branch = [b for b in sorted(commit_branches) if b.startswith('f')][-1]
        else:
            self.branch = commit_branches[0]

        if self.branch.startswith('f'):
            release_branch = self.branch
        else:
            release_branch = None

        updates = list_updates(updater.db_session, 'rpm', package, release_branch=release_branch)
        commit_to_update = {}
        for update_build, build in updates:
            if build.source is None:
                logger.warning("Ignoring build %s without source", update_build.build_nvr)
                continue
            c = _get_commit(build)
            c_branches = repo.get_branches(c)
            if self.branch in c_branches:
                commit_to_update[c] = (update_build.update, build)

        if self.commit not in commit_to_update:
            commit_to_update[self.commit] = (None, self.build)

        def compare_versions(a, b):
            return nvrcmp(commit_to_update[a][1].nvr, commit_to_update[b][1].nvr)

        nvr_order = sorted(commit_to_update.keys(),
                           key=functools.cmp_to_key(compare_versions),
                           reverse=True)

        try:
            ordered_commits = repo.order(commit_to_update.keys())
            ordered_commits.reverse()

            if nvr_order != ordered_commits:
                logger.warning("%s: NVR order %s differs from commit order %s", self.build.nvr,
                               [(c, commit_to_update[c][1].nvr) for c in nvr_order],
                               [(c, commit_to_update[c][1].nvr) for c in ordered_commits])
        except OrderingError:
            logger.info("%s: Failed to order based on git history, falling back to NVR comparison",
                        package.name)
            ordered_commits = nvr_order

        for c in ordered_commits:
            c_update, c_build = commit_to_update[c]
            if c_update and (c_update.status == 'stable' or c_update.status == 'testing'):
                self.items.append(PackageBuildInvestigationItem(c, c_build, c_update))
            elif c == self.commit:
                self.items.append(PackageBuildInvestigationItem(c, self.build, None))

            if c == self.commit:
                break

    def to_json(self):
        result = {
            'build': _build_to_json(self.build),
            'branch': self.branch,
            'commit': self.commit,
            'history': self.items,
        }
        if self.module_build:
            result['module_build'] = _build_to_json(self.module_build)
        return result


class FlatpakBuildInvestigation:
    def __init__(self, build, update):
        self.build = build
        self.update = update
        self.package_investigations = []

    def investigate(self, updater):
        for pb in self.build.list_package_builds():
            # Find the module that this package comes from, if any
            module_build = None
            for mb in self.build.module_builds:
                for mb_pb in mb.module_build.package_builds:
                    if mb_pb.package_build == pb.package_build:
                        module_build = mb.module_build

            key = (pb.package_build.nvr, module_build.nvr if module_build else None)
            package_investigation = updater.package_investigation_cache.get(key)
            if package_investigation is None:
                package_investigation = PackageBuildInvestigation(pb.package_build, module_build)
                package_investigation.investigate(updater)
                updater.package_investigation_cache[key] = package_investigation

            self.package_investigations.append(package_investigation)

        self.package_investigations.sort(key=lambda x: x.build.nvr.rsplit('-', 2)[0])

    def to_json(self):
        result = {
            'build': _build_to_json(self.build),
            'build_id': self.build.koji_build_id,
            'packages': self.package_investigations
        }

        if self.update is not None:
            result['update'] = _update_to_json(self.update)

        return result


class FlatpakInvestigation:
    def __init__(self, name, module_only=False):
        self.name = name
        self.flatpak = None
        self.module_only = module_only
        self.build_investigations = []

    def _add_build_investigation(self, build, update=None):
        for bi in self.build_investigations:
            if bi.build == build:
                if bi.update is None:
                    bi.update = update
                return

        self.build_investigations.append(FlatpakBuildInvestigation(build, update))

        def compare_versions(a, b):
            return nvrcmp(a.build.nvr, b.build.nvr)

        self.build_investigations.sort(key=functools.cmp_to_key(compare_versions), reverse=True)

    def _add_updates(self, updater):
        most_recent_testing = None
        most_recent_stable = None
        for update_build, build in list_updates(updater.db_session, 'flatpak', self.flatpak):
            update = update_build.update
            if update.status == 'pending':
                self._add_build_investigation(build, update)
            elif update.status == 'testing':
                if most_recent_testing is None or nvrcmp(most_recent_testing[0].nvr,
                                                         build.nvr) < 0:
                    most_recent_testing = (build, update)
            elif update.status == 'stable':
                if most_recent_stable is None or nvrcmp(most_recent_stable[0].nvr,
                                                        build.nvr) < 0:
                    most_recent_stable = (build, update)

        if most_recent_stable is not None:
            self._add_build_investigation(*most_recent_stable)
        if most_recent_testing is not None:
            self._add_build_investigation(*most_recent_testing)

    def _add_most_recent_build(self, updater):
        builds = list_flatpak_builds(updater.db_session, self.flatpak)
        if len(builds) == 0:
            return

        def compare_versions(build_a, build_b):
            return nvrcmp(build_a.nvr, build_b.nvr)

        most_recent = max(builds, key=functools.cmp_to_key(compare_versions))
        self._add_build_investigation(most_recent)

    def ensure_flatpak(self, updater):
        if self.flatpak is None:
            self.flatpak = Flatpak.get_for_name(updater.db_session,
                                                self.name,
                                                koji_session=updater.koji_session)
        return self.flatpak

    def investigate(self, updater):
        self.ensure_flatpak(updater)
        self._add_updates(updater)
        self._add_most_recent_build(updater)

    @property
    def packages(self):
        result = set()
        for bi in self.build_investigations:
            for pb in bi.build.package_builds:
                result.add(pb.package_build.package)

        return result

    def to_json(self):
        return {
            'name': self.name,
            'builds': self.build_investigations
        }


class Investigation:
    def __init__(self):
        self.flatpak_investigations = []

    def investigate(self, updater):
        # Make sure we have the most recent information about Flatpak updates
        refresh_all_updates(updater.koji_session, updater.db_session,
                            'flatpak')
        updater.db_session.commit()

        flatpak_names = set()
        for update_build, build in list_updates(updater.db_session, 'flatpak'):
            flatpak_names.add(build.nvr.rsplit('-', 2)[0])

        for name in sorted(flatpak_names):
            investigation = FlatpakInvestigation(name)
            self.flatpak_investigations.append(investigation)

        # Make sure we have the most recent information about Flatpak builds
        refresh_flatpak_builds(updater.koji_session, updater.db_session,
                               [i.ensure_flatpak(updater) for i in self.flatpak_investigations])
        updater.db_session.commit()

        packages = set()
        for investigation in self.flatpak_investigations:
            investigation.investigate(updater)
            packages.update(investigation.packages)
        updater.db_session.commit()

        # Now make sure we have the most recent git for relevant packages
        for p in sorted(packages, key=lambda p: p.name):
            updater.distgit.repo('rpms/' + p.name).mirror()

        # Make sure we have the most recent information about relevant packages
        refresh_updates(updater.koji_session, updater.db_session,
                        'rpm',
                        [p.name for p in packages])
        updater.db_session.commit()

        for investigation in self.flatpak_investigations:
            for bi in investigation.build_investigations:
                bi.investigate(updater)

    def to_json(self):
        return {
            'flatpaks': self.flatpak_investigations
        }


class UpdateJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, 'to_json'):
            return o.to_json()
