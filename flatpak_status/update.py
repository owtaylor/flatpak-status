#!/usr/bin/python3

from datetime import datetime
import functools
from functools import cached_property
import json
import logging
from urllib.parse import urlparse

from flatpak_indexer import release_info
from flatpak_indexer.bodhi_query import list_updates, refresh_all_updates, refresh_updates
from flatpak_indexer.build_cache import BuildCache
from flatpak_indexer.koji_query import (
    list_flatpak_builds, query_tag_builds,
    refresh_flatpak_builds, refresh_tag_builds
)
from flatpak_indexer.koji_utils import get_koji_session
from flatpak_indexer.models import FlatpakBuildModel
from flatpak_indexer.redis_utils import get_redis_client
from flatpak_indexer.release_info import ReleaseStatus
from rpm import labelCompare

from . import Modulemd
from .distgit import OrderingError

logger = logging.getLogger(__name__)


def nvrcmp(nvr_a, nvr_b):
    n_a, v_a, r_a = nvr_a.rsplit('-', 2)
    n_b, v_b, r_b = nvr_b.rsplit('-', 2)

    assert n_a == n_b

    return labelCompare(('0', v_a, r_a),
                        ('0', v_b, r_b))


class Updater:
    def __init__(self, config, distgit):
        self.config = config
        self.distgit = distgit
        self.package_investigation_cache = {}
        self.build_cache = BuildCache(self.config)

    @cached_property
    def redis_client(self):
        return get_redis_client(self.config)

    @cached_property
    def koji_session(self):
        return get_koji_session(self.config)


def _time_to_json(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _build_to_json(build, include_details=False):
    result = {
        'id': build.build_id,
        'nvr': build.nvr,
    }

    if include_details:
        result['user_name'] = build.user_name
        result['completion_time'] = _time_to_json(build.completion_time)

    return result


def _update_to_json(update, include_details=False):
    result = {
        'id': update.update_id,
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

    def find_branch(self, updater, repo):
        if self.module_stream is not None:
            # extract a ref from the modulemd
            rpm_component = self.module_stream.get_rpm_component(self.build.name)
            if rpm_component is None:
                raise RuntimeError(f"Cannot find {self.build.nvr} in the modulemd")

            ref = rpm_component.get_ref()
            branches = repo.get_branches(ref, try_mirroring=True)
            if ref in branches:
                return ref

            # ref was a commit ID

            # first return the oldest still-maintained release that contains the ref.
            maintained_branches = [r.branch for r in release_info.releases
                                   if r.branch in branches and r.status != ReleaseStatus.EOL]
            if len(maintained_branches) > 0:
                return maintained_branches[0]

            # then return the newest unmaintained branch
            all_branches = [r.branch for r in release_info.releases
                            if r.branch in branches]
            if len(all_branches) > 0:
                return all_branches[-1]

            # Can't find a branch at all - really should be a bad status, not a failure
            raise RuntimeError(
                f"{self.build.nvr} was built from ref: {ref}, no branch found")
        else:
            assert self.fallback_branch is not None

            return self.fallback_branch

    def investigate(self, updater):
        package_name = self.build.name
        repo = updater.distgit.repo('rpms/' + package_name)

        self.branch = self.find_branch(updater, repo)

        matching_releases = [r for r in release_info.releases if r.branch == self.branch]
        if len(matching_releases) > 0:
            release = matching_releases[0]
        else:
            raise RuntimeError(
                f"{self.build.nvr}: "
                "Cannot find matching release for branch {self.branch} - need stream branch support"
            )
            release = None

        if release.status == ReleaseStatus.EOL:
            release = [r for r in release_info.releases if r.status != ReleaseStatus.EOL][0]

        commits = {}

        if release.status != ReleaseStatus.RAWHIDE:
            updates = list_updates(updater.redis_client, 'rpm', package_name,
                                   release_branch=release.branch)
            for update in updates:
                for build_nvr in update.builds:
                    # Update might contain many other packages
                    build_name = build_nvr.rsplit('-', 2)[0]
                    if build_name != package_name:
                        continue

                    build = updater.build_cache.get_package_build(build_nvr)
                    if build.source is None:
                        logger.warning("Ignoring build %s without source", build_nvr)
                        continue
                    c = _get_commit(build)
                    c_branches = repo.get_branches(c, try_mirroring=True)
                    if self.branch in c_branches:
                        commits[c] = (update, build)

        tag_builds = query_tag_builds(updater.redis_client, release.tag,
                                      self.build.name)
        tag_builds.sort(key=functools.cmp_to_key(nvrcmp), reverse=True)
        if len(tag_builds) == 0:
            # Package introduced in updates, so just refer to the update builds
            tag_build_commit = None
        else:
            tag_build_nvr = tag_builds[0]

            tag_build_build = updater.build_cache.get_package_build(tag_build_nvr)
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
                        package_name)
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
                            package_name)
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

    def find_module(self, updater, package_build_nvr):
        module_build = None
        module_stream = None
        for mb_nvr in self.build.module_builds:
            mb = updater.build_cache.get_module_build(mb_nvr)
            for binary_package in mb.package_builds:
                if binary_package.source_nvr == package_build_nvr:
                    module_build = mb

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
        for binary_package in self.build.package_builds:
            # Find the module that this package comes from, if any

            package_build = updater.build_cache.get_package_build(binary_package.source_nvr)

            flatpak_name, flatpak_stream, _ = self.build.nvr.rsplit('-', 2)

            module_build, module_stream = self.find_module(updater, package_build.nvr)
            if module_build is None:
                if flatpak_name != 'flatpak-runtime' and flatpak_name != 'flatpak-sdk':
                    raise RuntimeError(
                        f"{self.build.nvr}: Can't find {package_build.nvr} in a module")
                fallback_branch = flatpak_stream
            else:
                fallback_branch = None

            key = (package_build.nvr,
                   module_build.nvr if module_build else None,
                   fallback_branch)
            package_investigation = updater.package_investigation_cache.get(key)
            if package_investigation is None:
                package_investigation = PackageBuildInvestigation(package_build,
                                                                  module_build, module_stream,
                                                                  fallback_branch)
                package_investigation.investigate(updater)
                updater.package_investigation_cache[key] = package_investigation

            self.package_investigations.append(package_investigation)

        self.package_investigations.sort(key=lambda x: x.build.name)

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
        self.module_only = module_only
        self.build_investigations = []

    def _add_build_investigation(self, build, update=None):
        for bi in self.build_investigations:
            if bi.build.nvr == build.nvr:
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

        for update in list_updates(updater.redis_client, 'flatpak', self.name):
            for build_nvr in update.builds:
                # Update might contain many other Flatpaks
                build_name = build_nvr.rsplit('-', 2)[0]
                if build_name != self.name:
                    continue

                build = updater.build_cache.get_image_build(build_nvr)
                assert isinstance(build, FlatpakBuildModel)
                stream = build_nvr.rsplit('-', 2)[1]

                if update.status == 'pending':
                    self._add_build_investigation(build, update)
                elif update.status == 'testing':
                    mrt_build, _ = most_recent_testing.get(stream, (None, None))
                    logger.warning("%s %s", mrt_build and mrt_build.nvr, build.nvr)
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
        builds = list_flatpak_builds(updater.koji_session, updater.redis_client, self.name)
        if len(builds) == 0:
            return

        def compare_versions(build_a, build_b):
            return nvrcmp(build_a.nvr, build_b.nvr)

        most_recent = max(builds, key=functools.cmp_to_key(compare_versions))
        self._add_build_investigation(most_recent)

    def investigate(self, updater):
        self._add_updates(updater)
        self._add_most_recent_build(updater)

    def list_packages(self, updater):
        result = set()
        for bi in self.build_investigations:
            for binary_package in bi.build.package_builds:
                package_build = updater.build_cache.get_package_build(binary_package.source_nvr)
                result.add(package_build.name)

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
        refresh_all_updates(updater.koji_session, updater.redis_client,
                            'flatpak')

        flatpak_names = set()
        for update in list_updates(updater.redis_client, 'flatpak'):
            for build in update.builds:
                flatpak_names.add(build.rsplit('-', 2)[0])

        for name in sorted(flatpak_names):
            investigation = FlatpakInvestigation(name)
            self.flatpak_investigations.append(investigation)

        # Make sure we have the most recent information about Flatpak builds
        refresh_flatpak_builds(updater.koji_session, updater.redis_client,
                               [i.name for i in self.flatpak_investigations])

        # And about the contents of relevant tags
        for release in release_info.releases:
            if release.status != ReleaseStatus.EOL:
                refresh_tag_builds(updater.koji_session, updater.redis_client, release.tag)

        packages = set()
        for investigation in self.flatpak_investigations:
            investigation.investigate(updater)
            packages.update(investigation.list_packages(updater))

        # Now make sure we have the most recent git for relevant packages
        for p in sorted(packages):
            updater.distgit.repo('rpms/' + p).mirror()

        # Make sure we have the most recent information about relevant packages
        refresh_updates(updater.koji_session, updater.redis_client,
                        'rpm',
                        list(packages))

        for investigation in self.flatpak_investigations:
            for bi in investigation.build_investigations:
                bi.investigate(updater)

    def to_json(self):
        return {
            'date_updated': _time_to_json(datetime.utcnow()),
            'flatpaks': self.flatpak_investigations,
        }


class UpdateJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, 'to_json'):
            return o.to_json()
