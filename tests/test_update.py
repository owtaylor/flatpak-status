import json

from flatpak_indexer.test.bodhi import mock_bodhi
from flatpak_indexer.test.koji import mock_koji
from flatpak_indexer.test.redis import mock_redis

from flatpak_status.cli import Config
from flatpak_status.update import Investigation, Session, UpdateJsonEncoder
from .distgit_mock import make_mock_distgit


CONFIG = """
cache_dir: cache
output: generated/status.json
koji_config: fedora
redis_url: redis://localhost:16379
redis_password: abc123
"""


@mock_bodhi
@mock_koji
@mock_redis
def test_flatpak_investigation():
    config = Config.from_str(CONFIG)
    distgit = make_mock_distgit()

    updater = Session(config, distgit)

    investigation = Investigation()
    investigation.investigate(updater)

    eog_investigation = [i for i in investigation.flatpak_investigations if i.name == 'eog'][0]

    packages = eog_investigation.list_packages(updater)
    assert set(packages) == {'eog', 'exempi', 'libpeas', 'gnome-desktop3'}

    assert len(eog_investigation.build_investigations) == 1
    bi = eog_investigation.build_investigations[0]
    assert bi.build.nvr == 'eog-master-20181128204005.1'

    assert ({pi.build.nvr.name for pi in bi.package_investigations} ==
            set(['eog', 'exempi', 'libpeas', 'gnome-desktop3']))

    eog_pi = next(pi for pi in bi.package_investigations if pi.build.nvr.name == 'eog')
    assert eog_pi.build.nvr.name == 'eog'
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
                             if pi.build.nvr.name == 'gnome-desktop3')
    assert gnome_desktop3_pi.build.nvr.name == 'gnome-desktop3'
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
                      if pi.build.nvr.name == 'libpeas')
    assert libpeas_pi.build.nvr.name == 'libpeas'
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

    # Make sure that the two investigations are the same, but account that
    # the time might have changed

    d1 = json.loads(as_json)
    d2 = json.loads(as_json2)
    # time might have changed
    del d1['date_updated']
    del d2['date_updated']

    assert d1 == d2
