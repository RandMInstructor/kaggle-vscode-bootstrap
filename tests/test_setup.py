import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from kaggle_vscode import setup_vscode


class SetupTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("kaggle_vscode.setup.ensure_code", return_value="code")
        self.ensure_code = patcher.start()
        self.addCleanup(patcher.stop)

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
        active._tunnel_token = None
        active.is_running.return_value = True
        client = MagicMock()
        client.return_value.get_secret.return_value = "secret-value"
        with patch.dict(sys.modules, {"kaggle_secrets": SimpleNamespace(UserSecretsClient=client)}):
            self.assertIs(setup_vscode(accept_license=True), active)

    @patch("kaggle_vscode.setup.os", SimpleNamespace(name="posix", environ=os.environ))
    @patch("kaggle_vscode.setup.require")
    @patch("kaggle_vscode.setup.authenticate_gh")
    @patch("kaggle_vscode.setup.tunnel._active", None)
    @patch("kaggle_vscode.setup.tunnel.VSCodeTunnel")
    def test_separate_secret_forwarding_and_install_opt_out(self, session, auth, require):
        client = MagicMock()
        client.return_value.get_secret.side_effect = ["github-secret", "tunnel-secret"]
        with patch.dict(sys.modules, {"kaggle_secrets": SimpleNamespace(UserSecretsClient=client)}):
            setup_vscode(tunnel_secret_name="TUNNEL", install_code=False, accept_license=True)
        self.ensure_code.assert_called_once_with("code", install=False)
        auth.assert_called_once_with("github-secret")
        session.return_value.start.assert_called_once_with(
            token="tunnel-secret", timeout=120, auth_timeout=600, accept_license=True)
