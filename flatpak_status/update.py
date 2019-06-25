#!/usr/bin/python3

import functools
import json
import logging
from urllib.parse import urlparse

from rpm import labelCompare

from . import Modulemd
from .bodhi_query import list_updates, refresh_all_updates, refresh_updates
from .distgit import OrderingError
from .koji_query import (list_flatpak_builds, query_build, query_tag_builds,
                         refresh_flatpak_builds, refresh_tag_builds)
from .models import Flatpak, Package, PackageBuild
from .release_info import ReleaseStatus

logger = logging.getLogger(__name__)


def nvrcmp(nvr_a, nvr_b):
    n_a, v_a, r_a = nvr_a.rsplit('-', 2)
    n_b, v_b, r_b = nvr_b.rsplit('-', 2)

    assert n_a == n_b

    return labelCompare(('0', v_a, r_a),
                        ('0', v_b, r_b))


class Updater:
    def __init__(self, db_session, koji_session, distgit, releases):
        self.db_session = db_session
        self.koji_session = koji_session
        self.distgit = distgit
        self.releases = releases
        self.package_investigation_cache = {}


def _time_to_json(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _build_to_json(build, include_details=False):
    result = {
        'id': build.koji_build_id,
        'nvr': build.nvr,
    }

    if include_details:
        result['user_name'] = build.user_name
        result['completion_time'] = _time_to_json(build.completion_time)

    return result


def _update_to_json(update, include_details=False):
    result = {
        'id': update.bodhi_update_id,
        'status': update.status,
        'type': update.type,
    }

    if include_details:
        result['user_name'] = update.user_name
        result['date_submitted'] = _time_to_json(update.date_submitted)

    return result


class PackageBuildInvestigationItem:
    def __init__(self, commit, build, update, is_release_version):
        self.commit = commit
        self.build = build
        self.update = update
        self.is_release_version = is_release_version

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
    if build.source:
        return urlparse(source).fragment
    else:
        return None


class PackageBuildInvestigation:
    def __init__(self, build, module_build, module_stream, fallback_branch):
        self.build = build
        self.module_build = module_build
        self.module_stream = module_stream
        self.fallback_branch = fallback_branch
        self.commit = _get_commit(build)
        self.branch = None
        self.items = []

    def find_branch(self, repo):
        n, v, r = self.build.nvr.rsplit('-', 2)

        if self.module_stream is not None:
            # extract a ref from the modulemd
            rpm_component = self.module_stream.get_rpm_component(n)
            if rpm_component is None:
                raise RuntimeError(f"Cannot find {self.build.nvr} in the modulemd")

            ref = rpm_component.get_ref()
            branches = repo.get_branches(ref)
            if ref in branches:
                return ref

            # ref was a commit ID. What we *should* return here is the oldest still-maintained
            # release that contains the ref.
            raise RuntimeError(
                f"{self.build.nvr} was built from ref: {ref}, can't determine branch")
        else:
            assert self.fallback_branch is not None

            return self.fallback_branch

    def investigate(self, updater):
        package = self.build.package
        repo = updater.distgit.repo('rpms/' + package.name)

        self.branch = self.find_branch(repo)

        matching_releases = [r for r in updater.releases if r.branch == self.branch]
        if len(matching_releases) > 0:
            release = matching_releases[0]
        else:
            raise RuntimeError(f"Branch {self.branch} not found - need stream branch support")
            release = None

        if release.status == ReleaseStatus.EOL:
            release = [r for r in updater.releases if r.status != ReleaseStatus.EOL][0]

        commits = {}

        if release.status != ReleaseStatus.RAWHIDE:
            updates = list_updates(updater.db_session, 'rpm', package,
                                   release_branch=release.branch)
            for update_build, build in updates:
                if build.source is None:
                    logger.warning("Ignoring build %s without source", update_build.build_nvr)
                    continue
                c = _get_commit(build)
                c_branches = repo.get_branches(c)
                if self.branch in c_branches:
                    commits[c] = (update_build.update, build)

        def compare_tag_build_versions(a, b):
            return nvrcmp(a.build_nvr, b.build_nvr)

        tag_builds = query_tag_builds(updater.db_session, release.tag,
                                      self.build.nvr.rsplit('-', 2)[0])
        tag_builds.sort(key=functools.cmp_to_key(compare_tag_build_versions),
                        reverse=True)
        if len(tag_builds) == 0:
            # Package introduced in updates, so just refer to the update builds
            tag_build_commit = None
        else:
            tag_build = tag_builds[0]

            tag_build_build = query_build(updater.koji_session, updater.db_session,
                                          tag_build.build_nvr, Package, PackageBuild)
            tag_build_commit = _get_commit(tag_build_build)
            if tag_build_commit not in commits:
                commits[tag_build_commit] = (None, tag_build_build)

        if self.commit not in commits:
            commits[self.commit] = (None, self.build)

        def compare_versions(a, b):
            return nvrcmp(commits[a][1].nvr, commits[b][1].nvr)

        nvr_order = sorted(commits.keys(),
                           key=functools.cmp_to_key(compare_versions),
                           reverse=True)

        git_commits = commits.keys()
        if None in git_commits:
            # Some build didn't have a source in Koji (if more than one build is missing a Koji
            # source, then our hash table doesn't work right... hopefully even rarer.)
            logger.info("%s: Don't have commit hashes for all builds, "
                        "falling back to NVR comparison",
                        package.name)
            ordered_commits = nvr_order
        else:
            try:
                ordered_commits = repo.order(commits.keys())
                ordered_commits.reverse()

                if nvr_order != ordered_commits:
                    logger.warning("%s: NVR order %s differs from commit order %s", self.build.nvr,
                                   [(c, commits[c][1].nvr) for c in nvr_order],
                                   [(c, commits[c][1].nvr) for c in ordered_commits])
            except OrderingError:
                logger.info("%s: Failed to order based on git history, "
                            "falling back to NVR comparison",
                            package.name)
                ordered_commits = nvr_order

        for c in ordered_commits:
            c_update, c_build = commits[c]
            if c_update and (c_update.status == 'stable' or c_update.status == 'testing'):
                self.items.append(PackageBuildInvestigationItem(c, c_build, c_update,
                                                                c == tag_build_commit))
            elif c == tag_build_commit:
                self.items.append(PackageBuildInvestigationItem(c, c_build, None, True))
            elif c == self.commit:
                self.items.append(PackageBuildInvestigationItem(c, self.build, None, False))

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
        self.module_to_module_stream = {}

    def find_module(self, package_build):
        module_build = None
        module_stream = None
        for mb in self.build.module_builds:
            for mb_pb in mb.module_build.package_builds:
                if mb_pb.package_build == package_build:
                    module_build = mb.module_build

        if module_build is not None:
            module_stream = self.module_to_module_stream.get(module_build.nvr)
            if module_stream is None:
                module_index = Modulemd.ModuleIndex.new()
                module_index.update_from_string(module_build.modulemd, strict=False)
                module_name, module_stream, _ = module_build.nvr.rsplit('-', 2)
                module_stream = module_index \
                    .get_module(module_name) \
                    .get_streams_by_stream_name(module_stream)[0]
                self.module_to_module_stream[module_build.nvr] = module_stream

        return module_build, module_stream

    def investigate(self, updater):
        for pb in self.build.list_package_builds():
            # Find the module that this package comes from, if any

            flatpak_name, flatpak_stream, _ = self.build.nvr.rsplit('-', 2)

            module_build, module_stream = self.find_module(pb.package_build)
            if module_build is None:
                if flatpak_name != 'flatpak-runtime' and flatpak_name != 'flatpak-sdk':
                    raise RuntimeError(
                        f"{self.build.nvr}: Can't find {pb.package_build.nvr} in a module")
                fallback_branch = flatpak_stream
            else:
                fallback_branch = None

            key = (pb.package_build.nvr,
                   module_build.nvr if module_build else None,
                   fallback_branch)
            package_investigation = updater.package_investigation_cache.get(key)
            if package_investigation is None:
                package_investigation = PackageBuildInvestigation(pb.package_build,
                                                                  module_build, module_stream,
                                                                  fallback_branch)
                package_investigation.investigate(updater)
                updater.package_investigation_cache[key] = package_investigation

            self.package_investigations.append(package_investigation)

        self.package_investigations.sort(key=lambda x: x.build.nvr.rsplit('-', 2)[0])

    def to_json(self):
        result = {
            'build': _build_to_json(self.build, include_details=True),
            'packages': self.package_investigations
        }

        if self.update is not None:
            result['update'] = _update_to_json(self.update, include_details=True)

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
        most_recent_testing = {}
        most_recent_stable = {}

        for update_build, build in list_updates(updater.db_session, 'flatpak', self.flatpak):
            stream = build.nvr.rsplit('-', 2)[1]

            update = update_build.update
            if update.status == 'pending':
                self._add_build_investigation(build, update)
            elif update.status == 'testing':
                mrt_build, _ = most_recent_testing.get(stream, (None, None))
                if mrt_build is None or nvrcmp(mrt_build.nvr, build.nvr) < 0:
                    most_recent_testing[stream] = (build, update)
            elif update.status == 'stable':
                mrs_build, _ = most_recent_stable.get(stream, (None, None))
                if mrs_build is None or nvrcmp(mrs_build.nvr, build.nvr) < 0:
                    most_recent_stable[stream] = (build, update)

        for build, update in most_recent_stable.values():
            self._add_build_investigation(build, update)
        for build, update in most_recent_testing.values():
            self._add_build_investigation(build, update)

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

        # And about the contents of relevant tags
        for release in updater.releases:
            if release.status != ReleaseStatus.EOL:
                refresh_tag_builds(updater.koji_session, updater.db_session, release.tag)

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
