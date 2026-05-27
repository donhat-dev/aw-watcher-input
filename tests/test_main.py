import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from click.testing import CliRunner

from aw_watcher_input import main as watcher_main


class MainTest(unittest.TestCase):
    def test_uses_local_listener_classes(self):
        self.assertEqual("aw_watcher_input.listeners", watcher_main.KeyboardListener.__module__)
        self.assertEqual("aw_watcher_input.listeners", watcher_main.MouseListener.__module__)

    def test_missing_macos_input_permission_exits_successfully_before_connecting(self):
        client = Mock(side_effect=AssertionError("ActivityWatchClient should not be created"))
        permission_state = SimpleNamespace(satisfied=False)

        with (
            patch.object(watcher_main.sys, "platform", "darwin"),
            patch.object(watcher_main, "_configure_logging"),
            patch.object(watcher_main, "_load_toml_config", return_value={}),
            patch.object(watcher_main, "ensure_macos_input_permissions", return_value=permission_state),
            patch.object(watcher_main.aw_client, "ActivityWatchClient", client),
        ):
            result = CliRunner().invoke(watcher_main.main, [])

        self.assertEqual(0, result.exit_code, result.output)
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
