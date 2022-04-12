from copy import deepcopy
import sys
from unittest.mock import patch

from click.testing import CliRunner
from flatpak_indexer import fedora_monitor
import pytest
import yaml


from flatpak_status.cli import cli, Config
from .bodhi import mock_bodhi
from .distgit_mock import mock_distgit
from .fedora_monitor_mock import mock_fedora_monitor
from .koji import mock_koji
from .redis import mock_redis


CONFIG = yaml.safe_load("""\
koji_config: fedora
redis_url: redis://localhost:16379
""")


@pytest.fixture
def config(tmp_path):
    config = deepcopy(CONFIG)
    config["cache_dir"] = str(tmp_path / "cache")
    config["output"] = str(tmp_path / "status.json")

    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f)

    return config_path


@mock_bodhi
@mock_distgit
@mock_fedora_monitor
@mock_koji
@mock_redis
@pytest.mark.parametrize('bodhi_changed,distgit_changed', [
    (None, None),
    (set(), set()),
    (set(['FEDORA-2018-ac69655fa3', 'NOTEXIST']), set(['rpms/eog', 'NOTEXIST'])),
])
def test_daemon(tmp_path, config, bodhi_changed, distgit_changed):
    config_object = Config.from_path(config)
    mock_fedora_monitor = fedora_monitor.FedoraMonitor(config_object)

    mock_fedora_monitor.get_bodhi_changed.return_value = (bodhi_changed, 42)
    mock_fedora_monitor.get_distgit_changed.return_value = (distgit_changed, 42)

    sleep_count = 0

    runner = CliRunner()

    def mock_sleep(secs):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == 2:
            sys.exit(42)

    with patch('time.sleep', side_effect=mock_sleep):
        result = runner.invoke(cli, ['--config-file', config, 'daemon'],
                               catch_exceptions=False)
        assert result.exit_code == 42
        assert result.output == ''

        assert (tmp_path / "status.json").exists()


@mock_bodhi
@mock_distgit
@mock_fedora_monitor
@mock_koji
@mock_redis
def test_daemon_exception(tmp_path, config, caplog):
    runner = CliRunner()

    def mock_sleep(secs):
        sys.exit(42)

    with patch('time.sleep', side_effect=mock_sleep), \
         patch("flatpak_status.update.Investigation.investigate",
               side_effect=RuntimeError("All Broken")):
        result = runner.invoke(cli, ['--config-file', config, 'daemon'],
                               catch_exceptions=False)
        assert "All Broken" in caplog.text
        assert result.exit_code == 42
        assert result.output == ''


@mock_bodhi
@mock_distgit
@mock_koji
@mock_redis
@pytest.mark.parametrize('verbose', [False, True])
def test_update(tmp_path, config, caplog, verbose):
    runner = CliRunner()

    options = ['--config-file', config]
    if verbose:
        options += ['--verbose']

    print(options + ['update'])
    result = runner.invoke(cli, options + ['update'], catch_exceptions=False)
    assert result.output == ''
    assert result.exit_code == 0

    if verbose:
        assert 'Successfully created json cache' in caplog.text
    else:
        assert 'Successfully created json cache' not in caplog.text

    assert (tmp_path / "status.json").exists()
