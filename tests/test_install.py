import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from kaggle_vscode.install import ensure_code


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as tar:
            member = tarfile.TarInfo("code")
            payload = b"standalone-cli"
            member.size = len(payload)
            tar.addfile(member, io.BytesIO(payload))
        self.archive = archive.getvalue()
        self.metadata = {"url": "https://vscode.download.prss.microsoft.com/test.tar.gz",
                         "version": "a" * 40,
                         "sha256hash": hashlib.sha256(self.archive).hexdigest()}
        for patcher in (patch("kaggle_vscode.install.shutil.which", return_value=None),
                        patch("kaggle_vscode.install.platform.system", return_value="Linux"),
                        patch("kaggle_vscode.install.platform.machine", return_value="x86_64"),
                        patch("kaggle_vscode.install.Path.home", return_value=self.home),
                        patch.dict(os.environ)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def responses(self):
        return [io.BytesIO(json.dumps(self.metadata).encode()), io.BytesIO(self.archive)]

    def test_verified_install_path_and_cache(self):
        with patch("kaggle_vscode.install.urlopen", side_effect=self.responses()) as fetch:
            binary = Path(ensure_code())
            self.assertEqual(binary.read_bytes(), b"standalone-cli")
            self.assertIn(str(binary.parent), os.environ["PATH"].split(os.pathsep))
            self.assertEqual(ensure_code(), str(binary))
            self.assertEqual(fetch.call_count, 2)

    def test_bad_checksum_does_not_install(self):
        self.metadata["sha256hash"] = "0" * 64
        with patch("kaggle_vscode.install.urlopen", side_effect=self.responses()):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                ensure_code()
        self.assertFalse((self.home / ".cache/kaggle-vscode/bin/code").exists())

    def test_existing_code_does_not_download(self):
        with patch("kaggle_vscode.install.shutil.which", return_value="/usr/bin/code"), patch("kaggle_vscode.install.urlopen") as fetch:
            self.assertEqual(ensure_code(), "/usr/bin/code")
            fetch.assert_not_called()

    def test_custom_path_and_opt_out(self):
        for code, install in (("/missing/code", True), ("code", False)):
            with self.assertRaisesRegex(RuntimeError, "Missing"):
                ensure_code(code, install=install)
