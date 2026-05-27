import unittest
import importlib.util
from pathlib import Path


def load_macos_permissions_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "aw_watcher_input"
        / "macos_permissions.py"
    )
    spec = importlib.util.spec_from_file_location("macos_permissions", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBackend:
    def __init__(self, listen_event=False, accessibility=False):
        self.listen_event = listen_event
        self.accessibility = accessibility
        self.requests = []

    def has_listen_event_access(self):
        return self.listen_event

    def has_accessibility_trust(self):
        return self.accessibility

    def request_listen_event_access(self):
        self.requests.append("listen_event")
        return False

    def request_accessibility_trust(self):
        self.requests.append("accessibility")
        return False


class MacosPermissionsTest(unittest.TestCase):
    def test_accessibility_satisfies_input_permission(self):
        module = load_macos_permissions_module()
        backend = FakeBackend(listen_event=False, accessibility=True)

        state = module.ensure_macos_input_permissions(platform="darwin", backend=backend)

        self.assertTrue(state.satisfied)
        self.assertEqual([], backend.requests)

    def test_missing_input_permission_requests_listen_event_then_accessibility(self):
        module = load_macos_permissions_module()
        backend = FakeBackend(listen_event=False, accessibility=False)

        state = module.ensure_macos_input_permissions(platform="darwin", backend=backend)

        self.assertFalse(state.satisfied)
        self.assertEqual(["listen_event", "accessibility"], backend.requests)

    def test_non_macos_skips_permission_requests(self):
        module = load_macos_permissions_module()
        backend = FakeBackend(listen_event=False, accessibility=False)

        state = module.ensure_macos_input_permissions(platform="linux", backend=backend)

        self.assertTrue(state.satisfied)
        self.assertEqual([], backend.requests)


if __name__ == "__main__":
    unittest.main()
