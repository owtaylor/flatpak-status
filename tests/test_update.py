import json

import responses

from flatpak_status.release_info import Release, ReleaseStatus
from flatpak_status.update import Investigation, UpdateJsonEncoder, Updater
from .bodhi import mock_bodhi
from .distgit_mock import make_mock_distgit
from .koji import make_koji_session


releases = [
    Release(name='F28', branch='f28', tag='f28', status=ReleaseStatus.GA),
    Release(name='F29', branch='f29', tag='f29', status=ReleaseStatus.GA),
]


@responses.activate
def test_flatpak_investigation(session):
    koji_session = make_koji_session()
    distgit = make_mock_distgit()
    mock_bodhi()

    updater = Updater(session, koji_session, distgit, releases)

    investigation = Investigation()
    investigation.investigate(updater)

    eog_investigation = [i for i in investigation.flatpak_investigations if i.name == 'eog'][0]

    packages = eog_investigation.packages
    assert {p.name for p in packages} == set(['eog', 'exempi', 'libpeas', 'gnome-desktop3'])

    assert len(eog_investigation.build_investigations) == 1
    bi = eog_investigation.build_investigations[0]
    assert bi.build.nvr == 'eog-master-20181128204005.1'

    assert ({pi.build.package.name for pi in bi.package_investigations} ==
            set(['eog', 'exempi', 'libpeas', 'gnome-desktop3']))

    eog_pi = next(pi for pi in bi.package_investigations if pi.build.package.name == 'eog')
    assert eog_pi.build.package.name == 'eog'
    assert eog_pi.branch == 'f29'
    assert eog_pi.commit == '9b072f23540e45282678d9397faa8e28982fcbbd'
    assert eog_pi.module_build.nvr == 'eog-master-20181128204005.775baa8e'
    assert len(eog_pi.items) == 1
    assert eog_pi.items[0].commit == '9b072f23540e45282678d9397faa8e28982fcbbd'
    assert eog_pi.items[0].build.nvr == 'eog-3.28.4-1.fc29'
    assert eog_pi.items[0].update.status == 'stable'
    assert eog_pi.items[0].is_release_version is True

    gnome_desktop3_pi = next(pi
                             for pi in bi.package_investigations
                             if pi.build.package.name == 'gnome-desktop3')
    assert gnome_desktop3_pi.build.package.name == 'gnome-desktop3'
    assert gnome_desktop3_pi.branch == 'f29'
    assert gnome_desktop3_pi.commit == '647d07b80231a012e94cef368750616ca7999b3b'
    assert gnome_desktop3_pi.module_build.nvr == 'eog-master-20181128204005.775baa8e'
    assert len(gnome_desktop3_pi.items) == 2
    assert gnome_desktop3_pi.items[0].commit == '802073589f1383c09e7b6f0e1c16972b1679d6c2'
    assert gnome_desktop3_pi.items[0].build.nvr == 'gnome-desktop3-3.30.2.1-1.fc29'
    assert gnome_desktop3_pi.items[0].update.status == 'stable'
    assert gnome_desktop3_pi.items[0].is_release_version is False
    assert gnome_desktop3_pi.items[1].commit == '647d07b80231a012e94cef368750616ca7999b3b'
    assert gnome_desktop3_pi.items[1].build.nvr == 'gnome-desktop3-3.30.2-1.fc29'
    assert gnome_desktop3_pi.items[1].update.status == 'stable'
    assert gnome_desktop3_pi.items[1].is_release_version is False

    libpeas_pi = next(pi
                      for pi in bi.package_investigations
                      if pi.build.package.name == 'libpeas')
    assert libpeas_pi.build.package.name == 'libpeas'
    assert libpeas_pi.branch == 'f29'
    assert libpeas_pi.commit == '8e162f875ac7e00dd90f3d791d40484f91012415'
    assert libpeas_pi.module_build.nvr == 'eog-master-20181128204005.775baa8e'
    assert len(libpeas_pi.items) == 1
    assert libpeas_pi.items[0].commit == '8e162f875ac7e00dd90f3d791d40484f91012415'
    assert libpeas_pi.items[0].build.nvr == 'libpeas-1.22.0-9.fc29'
    assert libpeas_pi.items[0].update is None
    assert libpeas_pi.items[0].is_release_version is True

    as_json = json.dumps(investigation, cls=UpdateJsonEncoder, indent=4)
    data = json.loads(as_json)

    feedreader_data = next(x for x in data['flatpaks'] if x['name'] == 'feedreader')

    assert feedreader_data['name'] == 'feedreader'
    assert len(feedreader_data['builds']) == 2

    build_data = feedreader_data['builds'][0]
    assert build_data['build']['nvr'] == 'feedreader-master-2920190201225359.1'

    # Try again, check for reduced network traffic

    investigation2 = Investigation()
    investigation2.investigate(updater)

    as_json2 = json.dumps(investigation2, cls=UpdateJsonEncoder, indent=4)

    # time might have changed
    del as_json['date_updated']
    del as_json2['date_updated']

    assert as_json2 == as_json
