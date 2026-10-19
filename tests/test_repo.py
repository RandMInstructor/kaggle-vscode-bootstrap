from pathlib import Path
import subprocess
import tempfile
import unittest
from kaggle_vscode import checkout_repo


class RepoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "project"
        self.path.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("remote", "add", "origin", "https://github.com/OWNER/project.git")
        (self.path / "file.txt").write_text("initial")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.git("branch", "feature/test")

    def tearDown(self):
        # Git object files can be read-only on Windows.
        import os, stat
        for root, dirs, files in os.walk(self.temp.name):
            for file in files:
                os.chmod(Path(root) / file, stat.S_IWRITE | stat.S_IREAD)
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True, check=True).stdout.strip()

    def test_reuse_and_local_branch(self):
        self.assertEqual(checkout_repo("OWNER/project", self.path, "feature/test"), self.path.resolve())
        self.assertEqual(self.git("branch", "--show-current"), "feature/test")

    def test_wrong_origin(self):
        with self.assertRaisesRegex(RuntimeError, "origin"):
            checkout_repo("OTHER/project", self.path)

    def test_dirty_branch_switch_preserves_work(self):
        (self.path / "file.txt").write_text("my work")
        with self.assertRaisesRegex(RuntimeError, "local changes"):
            checkout_repo("OWNER/project", self.path, "feature/test")
        self.assertEqual((self.path / "file.txt").read_text(), "my work")

    def test_reject_url(self):
        with self.assertRaises(ValueError):
            checkout_repo("https://token@github.com/OWNER/project")
