from datetime import datetime, timedelta, timezone
import logging

import koji

from .models import (BuildCacheItem,
                     Flatpak, FlatpakBuild, FlatpakBuildModuleBuild, FlatpakBuildPackageBuild,
                     Module, ModuleBuild, ModuleBuildPackageBuild,
                     Package, PackageBuild)

logger = logging.getLogger(__name__)

# This is the maximum amount of time we'll ask Koji for all new images.
# If we haven't updated our image information for longer than this, then
# we'll go Flatpak by Flatpak.
ALL_IMAGES_MAX_INTERVAL = timedelta(days=1)


# When querying Koji for events that happened since we last queried, we
# allow a timestamp offset of this much
TIMESTAMP_FUZZ = timedelta(minutes=1)


def _get_build(koji_session, session, build_info, entity, entity_cls, build_cls):
    if entity is None:
        entity = entity_cls.get_for_name(session,
                                         build_info['name'],
                                         package_id=build_info['package_id'])

    completion_time = datetime.fromtimestamp(build_info['completion_ts'], tz=timezone.utc)

    build = build_cls(entity=entity,
                      koji_build_id=build_info['build_id'],
                      nvr=build_info['nvr'],
                      source=build_info['source'],
                      completion_time=completion_time)
    session.add(build)

    if entity_cls == Flatpak:
        logger.info("Calling koji.listArchives(%s); nvr=%s",
                    build_info['build_id'], build_info['nvr'])
        archives = koji_session.listArchives(build_info['build_id'])
        # Archives should differ only in architecture
        archive = [a for a in archives if a['extra']['image']['arch'] == 'x86_64'][0]
        logger.info("Calling koji.listRPMs(%s)", archive['id'])
        components = koji_session.listRPMs(imageID=archive['id'])

        seen = set()
        for c in components:
            if c['build_id'] in seen:
                continue
            seen.add(c['build_id'])
            package_build = query_build_by_id(koji_session, session, c['build_id'],
                                              Package, PackageBuild, nvr=c['nvr'])
            session.add(FlatpakBuildPackageBuild(flatpak_build=build, package_build=package_build))

        for m in build_info['extra']['image']['modules']:
            module_build = query_build(koji_session, session, m, Module, ModuleBuild)
            session.add(FlatpakBuildModuleBuild(flatpak_build=build, module_build=module_build))
    elif entity_cls == Module:
        logger.info("Calling koji.listArchives(%s); nvr=%s",
                    build_info['build_id'], build_info['nvr'])
        archives = koji_session.listArchives(build_info['build_id'])
        # The RPM list for the 'modulemd.txt' archive has all the RPMs, recent
        # versions of MBS also write upload 'modulemd.<arch>.txt' archives with
        # architecture subsets.
        archives = [a for a in archives if a['filename'] == 'modulemd.txt']
        assert len(archives) == 1
        logger.info("Calling koji.listRPMs(%s)", archives[0]['id'])
        components = koji_session.listRPMs(imageID=archives[0]['id'])

        seen = set()
        for c in components:
            if c['build_id'] in seen:
                continue
            seen.add(c['build_id'])
            package_build = query_build_by_id(koji_session, session, c['build_id'],
                                              Package, PackageBuild, nvr=c['nvr'])
            session.add(ModuleBuildPackageBuild(module_build=build, package_build=package_build))

    return build


def _query_flatpak_builds(koji_session, session,
                          flatpak=None, include_only=None, complete_after=None):
    kwargs = {
        'type': Flatpak.koji_type,
        'state': koji.BUILD_STATES['COMPLETE']
    }

    if flatpak is not None:
        kwargs['packageID'] = flatpak.koji_package_id
    if complete_after is not None:
        kwargs['completeAfter'] = complete_after.replace(tzinfo=timezone.utc).timestamp()

    result = []
    logger.info("Calling koji.listBuilds(%s)", kwargs)
    builds = koji_session.listBuilds(**kwargs)
    for build_info in builds:
        if include_only is not None and not build_info['name'] in include_only:
            continue

        build = session.query(FlatpakBuild).filter_by(nvr=build_info['nvr']).first()
        if build is None:
            build = _get_build(koji_session, session, build_info, flatpak, Flatpak, FlatpakBuild)

        result.append(build)

    return result


def refresh_flatpak_builds(koji_session, session, flatpaks):
    to_query = {f.name: f for f in flatpaks}
    to_refresh = {}

    items = {i.package_name: i
             for i in session.query(BuildCacheItem).filter_by(koji_type=Flatpak.koji_type).all()
             if i.package_name in to_query}

    current_ts = datetime.utcnow()
    if len(items) > 0:
        refresh_ts = max(item.last_queried for item in items.values())

        if current_ts - refresh_ts < ALL_IMAGES_MAX_INTERVAL:
            for item in items.values():
                if item.package_name in to_query:
                    if item.last_queried == refresh_ts:
                        to_refresh[item.package_name] = to_query[item.package_name]
                        del to_query[item.package_name]

            if len(to_refresh) > 0:
                _query_flatpak_builds(koji_session, session, include_only=to_refresh,
                                      complete_after=refresh_ts - TIMESTAMP_FUZZ)

    for flatpak in to_query.values():
        _query_flatpak_builds(koji_session, session, flatpak=flatpak)

    # update the cache items so we know when we last queried
    for item in items.values():
        item.last_queried = current_ts

    for flatpak in flatpaks:
        if flatpak.name not in items:
            item = BuildCacheItem(package_name=flatpak.name,
                                  koji_type=Flatpak.koji_type,
                                  last_queried=current_ts)
            session.add(item)


def list_flatpak_builds(session, flatpak):
    return session.query(FlatpakBuild).filter_by(entity=flatpak).all()


def query_module_build_no_context(koji_session, session, nvr):
    n, v, r = nvr.rsplit('-', 2)

    old_build = session.query(ModuleBuild).filter(ModuleBuild.nvr.startswith(nvr)).first()
    if old_build:
        return old_build

    module = Module.get_for_name(session, n, koji_session=koji_session)
    builds = koji_session.listBuilds(packageID=module.koji_package_id,
                                     type=Module.koji_type)
    builds = [b for b in builds if b['nvr'].startswith(nvr)]
    if len(builds) == 0:
        raise RuntimeError(f"Could not look up {nvr} in Koji")
    elif len(builds) > 1:
        raise RuntimeError("More than one context for {nvr}!")

    return _get_build(koji_session, session, builds[0], module, Module, ModuleBuild)


def query_build(koji_session, session, nvr, entity_cls, build_cls):
    if entity_cls is Module:
        n, v, r = nvr.rsplit('-', 2)
        if '.' not in r:
            return query_module_build_no_context(koji_session, session, nvr)

    old_build = session.query(build_cls).filter_by(nvr=nvr).first()
    if old_build:
        return old_build

    logger.info("Calling koji.getBuild(%s)", nvr)
    build_info = koji_session.getBuild(nvr)
    if build_info is None:
        raise RuntimeError(f"Could not look up {nvr} in Koji")

    return _get_build(koji_session, session, build_info, None, entity_cls, build_cls)


def query_build_by_id(koji_session, session, build_id, entity_cls, build_cls,
                      nvr=None):
    old_build = session.query(build_cls).filter_by(koji_build_id=build_id).first()
    if old_build:
        return old_build

    if nvr:
        logger.info("Calling koji.getBuild(%s); nvr=%s", build_id, nvr)
    else:
        logger.info("Calling koji.getBuild(%s)", build_id)
    build_info = koji_session.getBuild(build_id)
    if build_info is None:
        raise RuntimeError(f"Could not look up {build_id} in Koji")

    return _get_build(koji_session, session, build_info, None, entity_cls, build_cls)
