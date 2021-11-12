from datetime import datetime, timedelta, timezone
import logging

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from sqlalchemy.orm import joinedload

from . import release_info
from .koji_query import query_build
from .models import (Flatpak, FlatpakBuild, FlatpakUpdate, FlatpakUpdateBuild,
                     Package, PackageBuild, PackageUpdate, PackageUpdateBuild,
                     UpdateCacheItem)
from .release_info import ReleaseStatus

logger = logging.getLogger(__name__)


# This is the maximum amount of time we'll ask Bodhi for all new updates
# of a given type; if we haven't updated our image information for longer
# than this, then we request package by package
#
# This is not typically hit - we'll refresh everything if our fedora-messaging
# queue has been garbage collected.
ALL_UPDATES_MAX_INTERVAL = timedelta(days=1)


# When querying Koji for events that happened since we last queried, we
# allow a timestamp offset of this much
TIMESTAMP_FUZZ = timedelta(minutes=1)


def parse_date_value(value):
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)


def _get_retrying_session():
    s = requests.Session()

    retries = Retry(total=5,
                    backoff_factor=0.1,
                    status_forcelist=[500, 502, 503, 504])

    s.mount('https://', HTTPAdapter(max_retries=retries))

    return s


def _run_query_and_insert(koji_session, db_session, requests_session,
                          content_type, url, params, save_packages):

    if content_type == 'rpm':
        update_cls = PackageUpdate
        update_build_cls = PackageUpdateBuild
        build_cls = PackageBuild
        entity_cls = Package
    elif content_type == 'flatpak':
        update_cls = FlatpakUpdate
        update_build_cls = FlatpakUpdateBuild
        build_cls = FlatpakBuild
        entity_cls = Flatpak
    else:
        raise RuntimeError(f"Unknown content_type {content_type}")

    # Depending on our query parameters, we might get duplicates in the response, and might
    # get less than rows_per_page rows in the response
    # (https://github.com/fedora-infra/bodhi/issues/4130),
    # so we need to track what updates we actually get to compare to 'total' in the
    # response, which is de-duplicated
    seen_updates = set()
    page = 1
    while True:
        params['page'] = page
        logger.info("Querying Bodhi with params: %s", params)

        response = requests_session.get(url,
                                        headers={'Accept': 'application/json'},
                                        params=params)
        response.raise_for_status()
        response_json = response.json()

        for update_json in response_json['updates']:
            update_id = update_json['updateid']
            if update_id in seen_updates:
                continue

            seen_updates.add(update_id)

            # Skip updates for EPEL
            release_name = update_json['release']['name']
            if release_name.startswith('EPEL-') or release_name.startswith('EL-'):
                continue

            found_build = False
            for build_json in update_json['builds']:
                package_name = build_json['nvr'].rsplit('-', 2)[0]
                if (build_json['type'] == content_type and
                        (save_packages is None or package_name in save_packages)):
                    found_build = True
            if not found_build:
                continue

            update = db_session.query(update_cls) \
                               .filter_by(bodhi_update_id=update_id) \
                               .first()
            if update is None:
                update = update_cls(bodhi_update_id=update_id,
                                    release_name=update_json['release']['name'],
                                    release_branch=update_json['release']['branch'],
                                    date_submitted=parse_date_value(update_json['date_submitted']),
                                    user_name=update_json['user']['name'],
                                    status=update_json['status'],
                                    type=update_json['type'])
                db_session.add(update)
            else:
                update.status = update_json['status']
                update.type = update_json['type']

            old_builds = {b.build_nvr: b for b in update.builds}
            for build_json in update_json['builds']:
                nvr = build_json['nvr']
                if nvr in old_builds:
                    del old_builds[nvr]
                else:
                    entity_name = nvr.rsplit('-', 2)[0]
                    update_build = update_build_cls(update=update,
                                                    build_nvr=nvr,
                                                    entity_name=entity_name)

                    db_session.add(update_build)
                    if save_packages is None or entity_name in save_packages:
                        query_build(koji_session, db_session, nvr, entity_cls, build_cls)

            for b in old_builds.values():
                db_session.delete(b)

        # The first check avoids an extra round trip in the normal case, the second check
        # avoids paging forever if something goes wrong
        if len(seen_updates) >= response_json['total'] or len(response_json['updates']) == 0:
            break
        else:
            page += 1


def _query_updates(koji_session, db_session, requests_session,
                   content_type,
                   query_packages=None,
                   save_packages=None,
                   after=None,
                   rows_per_page=100):

    url = "https://bodhi.fedoraproject.org/updates/"
    params = {
        'rows_per_page': rows_per_page,
    }

    bodhi_releases = []
    for release in release_info.releases:
        if release.status == ReleaseStatus.EOL or release.status == ReleaseStatus.RAWHIDE:
            continue

        bodhi_release = release.name
        if content_type == 'flatpak':
            bodhi_release += 'F'
        bodhi_releases.append(bodhi_release)
    params['releases'] = bodhi_releases

    # Setting the content type in the query:
    #
    # a) messes up the pagination in the query
    # (https://github.com/fedora-infra/bodhi/issues/4130)
    #
    # b) can make things much slower
    # (https://github.com/fedora-infra/bodhi/issues/3064)
    #
    # params['content_type'] = content_type
    #
    # For Fedora, because each content type has a separate release, we effectively
    # filter by content type anyways.

    if query_packages is not None:
        if len(query_packages) > 5:
            for i in range(0, len(query_packages), 5):
                _query_updates(koji_session, db_session, requests_session,
                               content_type,
                               query_packages=query_packages[i:i+5],
                               save_packages=save_packages,
                               after=after,
                               rows_per_page=rows_per_page)
            return
        else:
            params['packages'] = query_packages

    if after is not None:
        for key in ['submitted_since', 'modified_since']:
            params_copy = dict(params)
            params_copy[key] = (after - TIMESTAMP_FUZZ).isoformat()

            _run_query_and_insert(koji_session, db_session, requests_session,
                                  content_type,
                                  url, params_copy, save_packages)
    else:
        _run_query_and_insert(koji_session, db_session, requests_session,
                              content_type,
                              url, params, save_packages)


def refresh_updates(koji_session, db_session,
                    content_type, packages, rows_per_page=10):
    requests_session = _get_retrying_session()

    to_query = set(packages)
    to_refresh = set()

    cache_items = {i.package_name: i
                   for i in db_session.query(UpdateCacheItem)
                                      .filter_by(content_type=content_type)
                                      .all()
                   if i.package_name in packages}

    current_ts = datetime.utcnow()
    if len(cache_items) > 0:
        refresh_ts = max(item.last_queried for item in cache_items.values())

        if current_ts - refresh_ts < ALL_UPDATES_MAX_INTERVAL:
            for item in cache_items.values():
                if item.package_name in to_query:
                    if item.last_queried == refresh_ts:
                        to_refresh.add(item.package_name)
                        to_query.remove(item.package_name)

        if len(to_refresh) > 0:
            _query_updates(koji_session, db_session, requests_session,
                           content_type,
                           save_packages=to_refresh,
                           after=refresh_ts - TIMESTAMP_FUZZ,
                           rows_per_page=rows_per_page)

    if len(to_query) > 0:
        _query_updates(koji_session, db_session, requests_session,
                       content_type,
                       query_packages=sorted(to_query),
                       save_packages=to_query,
                       rows_per_page=rows_per_page)

    # update the cache items so we know when we last queried
    for item in cache_items.values():
        item.last_queried = current_ts

    for package in packages:
        if package not in cache_items:
            item = UpdateCacheItem(package_name=package,
                                   content_type=content_type,
                                   last_queried=current_ts)
            db_session.add(item)


def refresh_all_updates(koji_session, db_session,
                        content_type, rows_per_page=10):
    requests_session = _get_retrying_session()

    cache_item = db_session.query(UpdateCacheItem) \
                           .filter_by(content_type=content_type,
                                      package_name='@ALL@') \
                           .first()

    current_ts = datetime.utcnow()
    if cache_item:
        after = cache_item.last_queried - TIMESTAMP_FUZZ
    else:
        after = None

    _query_updates(koji_session, db_session, requests_session,
                   content_type,
                   after=after,
                   rows_per_page=rows_per_page)

    if cache_item:
        cache_item.last_queried = current_ts
    else:
        cache_item = UpdateCacheItem(package_name='@ALL@',
                                     content_type=content_type,
                                     last_queried=current_ts)
        db_session.add(cache_item)


def refresh_update_status(koji_session, db_session, update_id):
    """Refreshes the status of a single update"""
    url = f"https://bodhi.fedoraproject.org/updates/{update_id}"
    requests_session = _get_retrying_session()

    update = db_session.query(PackageUpdate) \
                       .filter_by(bodhi_update_id=update_id) \
                       .first()
    if update is None:
        update = db_session.query(FlatpakUpdate) \
                           .filter_by(bodhi_update_id=update_id) \
                           .first()

    if update is None:
        logger.info("Update %s not found, no need to update status", update_id)
        return

    logger.info("Querying bodhi for the new status of: %s", update_id)
    response = requests_session.get(url,
                                    headers={'Accept': 'application/json'})
    response.raise_for_status()

    update.status = response.json()['update']['status']


def reset_update_cache(db_session):
    db_session.query(UpdateCacheItem).delete()


def list_updates(db_session, content_type, entity=None, release_branch=None):
    if release_branch is not None:
        branches = [release_branch]
    else:
        branches = [release.branch for release in release_info.releases
                    if release.status != ReleaseStatus.EOL and
                    release.status != ReleaseStatus.RAWHIDE]

    """ Returns a list of (PackageUpdateBuild, PackageBuild)"""
    if content_type == 'rpm':
        q = db_session.query(PackageUpdateBuild) \
            .join(PackageBuild, PackageBuild.nvr == PackageUpdateBuild.build_nvr) \
            .join(PackageUpdateBuild.update) \
            .filter(PackageUpdate.release_branch.in_(branches)) \
            .add_entity(PackageBuild)
        # We used to use .options(joinedload(PackageUpdateBuild.update)), but
        # with sqlalchemy-1.4.x, we need to put lazy='joined' on the relationship
        # instead, see https://github.com/sqlalchemy/sqlalchemy/issues/7318
        if entity is not None:
            q = q.filter(PackageUpdateBuild.entity_name == entity.name)

    elif content_type == 'flatpak':
        q = db_session.query(FlatpakUpdateBuild) \
            .join(FlatpakBuild, FlatpakBuild.nvr == FlatpakUpdateBuild.build_nvr) \
            .join(FlatpakUpdateBuild.update) \
            .filter(FlatpakUpdate.release_branch.in_(branches)) \
            .add_entity(FlatpakBuild)
        if entity is not None:
            q = q.filter(FlatpakUpdateBuild.entity_name == entity.name)

    return q.all()
