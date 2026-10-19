import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from kaggle_vscode import setup_vscode


class SetupTests(unittest.TestCase):
    @patch("kaggle_vscode.setup.os", SimpleNamespace(name="posix", environ=os.environ))
    @patch("kaggle_vscode.setup.require")
    @patch("kaggle_vscode.setup.authenticate_gh")
    def test_secret_failure_is_sanitized(self, auth, require):
        client = MagicMock()
        client.return_value.get_secret.side_effect = RuntimeError("secret-value")
        with patch.dict(sys.modules, {"kaggle_secrets": SimpleNamespace(UserSecretsClient=client)}):
            with self.assertRaisesRegex(RuntimeError, "Could not retrieve") as error:
                setup_vscode(accept_license=True)
        self.assertNotIn("secret-value", str(error.exception))
        auth.assert_not_called()

    @patch("kaggle_vscode.setup.os", SimpleNamespace(name="posix", environ=os.environ))
    @patch("kaggle_vscode.setup.require")
    @patch("kaggle_vscode.setup.authenticate_gh")
    @patch("kaggle_vscode.setup.tunnel._active")
    @patch.dict(os.environ, {"GH_TOKEN": "secret-value"})
    def test_repeat_reuses_active(self, active, auth, require):
        from pathlib import Path
        active.name = "kaggle-gpu"
        active.workspace = Path.cwd()
        active.code = "code"
        active._token = "secret-value"
        active.is_running.return_value = True
        client = MagicMock()
        client.return_value.get_secret.return_value = "secret-value"
        with patch.dict(sys.modules, {"kaggle_secrets": SimpleNamespace(UserSecretsClient=client)}):
            self.assertIs(setup_vscode(accept_license=True), active)
