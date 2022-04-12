from functools import wraps
from unittest.mock import create_autospec, Mock, patch


from flatpak_indexer.fedora_monitor import FedoraMonitor


def make_mock_monitor():
    monitor = create_autospec(FedoraMonitor)
    monitor.get_bodhi_changed = Mock(return_value=(set(), 42))
    monitor.get_distgit_changed = Mock(return_value=(set(), 42))

    return monitor


def mock_fedora_monitor(f):
    mock_monitor = make_mock_monitor()

    @wraps(f)
    def wrapper(*args, **kwargs):
        with patch('flatpak_indexer.fedora_monitor.FedoraMonitor', return_value=mock_monitor):
            return f(*args, **kwargs)

    return wrapper
