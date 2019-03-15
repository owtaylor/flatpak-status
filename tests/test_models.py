from datetime import datetime

from flatpak_status.models import Flatpak, FlatpakBuild, Module, ModuleBuild


MODULEMD = '''\
name: eog
stream: master
'''


def test_module(session):
    f = Module(name='eog', koji_package_id=303)
    session.add(f)
    f2 = Module.get_for_name(session, 'eog', package_id=303)
    assert f2 is f

    fb = ModuleBuild(entity=f, nvr='eog-master-12345.212321', koji_build_id=12345,
                     source="https://src.fedoraproject.org/modules/eog.git?#abcd1234",
                     user_name='otaylor',
                     completion_time=datetime.now(),
                     modulemd=MODULEMD)
    session.add(f)

    assert f.builds == [fb]


def test_flatpak(session):
    f = Flatpak(name='eog', koji_package_id=303)
    session.add(f)
    f2 = Flatpak.get_for_name(session, 'eog', package_id=303)
    assert f2 is f

    fb = FlatpakBuild(entity=f, nvr='eog-master-12345.2', koji_build_id=12345,
                      source="https://src.fedoraproject.org/flatpaks/eog.git?#abcd1234",
                      user_name='otaylor',
                      completion_time=datetime.now())
    session.add(f)

    assert f.builds == [fb]
