from flatpak_status.koji_query import (list_flatpak_builds, query_build, query_tag_builds,
                                       refresh_flatpak_builds, refresh_tag_builds)
from flatpak_status.models import Flatpak, FlatpakBuild
from .koji import make_koji_session


def test_query_builds(session):
    def sort_builds(builds):
        builds.sort(key=lambda x: x.koji_build_id)

    koji_session = make_koji_session()

    eog_flatpak = Flatpak.get_for_name(session, 'eog', koji_session=koji_session)
    quadrapassel_flatpak = Flatpak.get_for_name(session, 'quadrapassel', koji_session=koji_session)

    # First try, we query from scratch from Koji
    refresh_flatpak_builds(koji_session, session, [eog_flatpak])
    builds = list_flatpak_builds(session, eog_flatpak)
    sort_builds(builds)
    assert len(builds) == 2
    assert isinstance(builds[0], FlatpakBuild)
    assert builds[0].nvr == 'eog-master-20180821163756.2'
    assert builds[0].user_name == 'otaylor'
    assert builds[0].completion_time.strftime("%Y-%m-%d %H:%M:%S") == '2018-10-08 14:01:05'

    refresh_flatpak_builds(koji_session, session, [eog_flatpak, quadrapassel_flatpak])

    new_builds = list_flatpak_builds(session, eog_flatpak)
    sort_builds(new_builds)
    assert len(new_builds) == 2
    assert new_builds[0] is builds[0]
    assert new_builds[1] is builds[1]

    new_builds = list_flatpak_builds(session, quadrapassel_flatpak)
    assert len(new_builds) == 1
    assert new_builds[0].nvr == 'quadrapassel-master-20181203181243.2'


def test_query_build(session):
    koji_session = make_koji_session()

    build = query_build(koji_session, session, 'eog-master-20181128204005.1',
                        Flatpak, FlatpakBuild)
    assert build
    assert isinstance(build, FlatpakBuild)
    assert build.nvr == 'eog-master-20181128204005.1'

    # Try again and make sure we get the existing object from the database
    new_build = query_build(koji_session, session, 'eog-master-20181128204005.1',
                            Flatpak, FlatpakBuild)
    assert new_build is build


def test_query_tag_builds(session):
    koji_session = make_koji_session()

    refresh_tag_builds(koji_session, session, 'f28')
    builds = query_tag_builds(session, 'f28', 'quadrapassel')

    build_names = sorted(b.build_nvr for b in builds)
    assert build_names == [
        'quadrapassel-3.22.0-2.fc26',
        'quadrapassel-3.22.0-5.fc28',
        'quadrapassel-3.22.0-6.fc28',
    ]

    b = [b for b in builds if b.build_nvr == 'quadrapassel-3.22.0-6.fc28'][0]
    assert b.tag == 'f28'
    assert b.build_nvr == 'quadrapassel-3.22.0-6.fc28'
    assert b.entity_name == 'quadrapassel'


def test_query_tag_builds_incremental(session):
    # Start off with a koji session that will return tag history
    # mid-way through the f28 development cycle
    koji_session = make_koji_session(tagQueryTimestamp=1521520000)

    refresh_tag_builds(koji_session, session, 'f28')

    builds = query_tag_builds(session, 'f28', 'gnome-desktop3')
    build_names = sorted(b.build_nvr for b in builds)
    assert build_names == [
        'gnome-desktop3-3.26.1-1.fc28',
        'gnome-desktop3-3.26.2-1.fc28',
        'gnome-desktop3-3.27.90-1.fc28',
    ]

    # Now switch to a koji session without that limitation,
    # check that when we refresh, we add and remove builds properly
    koji_session = make_koji_session()

    refresh_tag_builds(koji_session, session, 'f28')

    builds = query_tag_builds(session, 'f28', 'gnome-desktop3')
    build_names = sorted(b.build_nvr for b in builds)
    assert build_names == [
        'gnome-desktop3-3.27.90-1.fc28',
        'gnome-desktop3-3.28.0-1.fc28',
        'gnome-desktop3-3.28.1-1.fc28',
    ]
