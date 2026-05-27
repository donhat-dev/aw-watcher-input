import unittest
from pathlib import Path


class PackagingSpecTest(unittest.TestCase):
    def test_pyinstaller_hiddenimports_are_platform_scoped(self):
        spec = (Path(__file__).resolve().parents[1] / "aw-watcher-input.spec").read_text(
            encoding="utf-8"
        )

        self.assertIn("target = platform.system()", spec)
        self.assertIn("if target == 'Linux':", spec)
        self.assertIn("elif target == 'Windows':", spec)
        self.assertIn("elif target == 'Darwin':", spec)

        linux_block = spec.split("if target == 'Linux':", 1)[1].split(
            "elif target == 'Windows':", 1
        )[0]
        windows_block = spec.split("elif target == 'Windows':", 1)[1].split(
            "elif target == 'Darwin':", 1
        )[0]
        darwin_block = spec.split("elif target == 'Darwin':", 1)[1].split(
            "a = Analysis", 1
        )[0]

        self.assertIn("'Xlib.keysymdef.miscellany'", linux_block)
        self.assertIn("'pynput.keyboard._darwin'", darwin_block)
        self.assertNotIn("'Xlib.keysymdef.miscellany'", darwin_block)
        self.assertNotIn("'win32timezone'", spec)


if __name__ == "__main__":
    unittest.main()
