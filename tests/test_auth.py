import os
import subprocess
import unittest
from unittest.mock import patch
from kaggle_vscode import authenticate_gh


class AuthTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("kaggle_vscode.auth.shutil.which", return_value="gh")
    @patch("kaggle_vscode.auth.subprocess.run")
    def test_environment_only_and_commit_after_validation(self, run, which):
        run.return_value.stdout = "example-user\n"
        self.assertEqual(authenticate_gh("test-secret"), "example-user")
        self.assertEqual(os.environ["GH_TOKEN"], "test-secret")
        for call in run.call_args_list:
            self.assertNotIn("test-secret", repr(call.args))
            self.assertEqual(call.kwargs["env"]["GH_TOKEN"], "test-secret")

    @patch.dict(os.environ, {"GH_TOKEN": "original"}, clear=True)
    @patch("kaggle_vscode.auth.shutil.which", return_value="gh")
    @patch("kaggle_vscode.auth.subprocess.run")
    def test_failure_redacts_and_preserves_environment(self, run, which):
        run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="test-secret")
        with self.assertRaises(RuntimeError) as error:
            authenticate_gh("test-secret")
        self.assertNotIn("test-secret", str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)
        self.assertEqual(os.environ["GH_TOKEN"], "original")

    def test_empty_token(self):
        for token in (None, "", "  "):
            with self.assertRaises(ValueError):
                authenticate_gh(token)

    @patch("kaggle_vscode.auth.shutil.which", return_value=None)
    def test_missing_cli(self, which):
        with self.assertRaisesRegex(RuntimeError, "Missing gh"):
            authenticate_gh("test-secret")
