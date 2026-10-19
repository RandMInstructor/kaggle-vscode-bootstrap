import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from kaggle_vscode import VSCodeTunnel


@unittest.skipUnless(os.name == "posix", "Linux process groups required")
class TunnelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.code = self.root / "code"
        self.code.write_text('''#!/usr/bin/env python3
import os, signal, subprocess, sys, time
if "--help" in sys.argv: sys.exit(0)
if "user" in sys.argv:
    assert os.environ.get("VSCODE_CLI_ACCESS_TOKEN")
    if os.environ.get("FAKE_LOGIN_FAIL"):
        print(os.environ["VSCODE_CLI_ACCESS_TOKEN"], flush=True)
        sys.exit(1)
    sys.exit(0)
print("inherited=" + str(bool(os.environ.get("GH_TOKEN"))), flush=True)
print("vscode_pat=" + str("VSCODE_CLI_ACCESS_TOKEN" in os.environ), flush=True)
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1000)"])
print("child=" + str(child.pid), flush=True)
def shutdown(*args):
    child.terminate()
    child.wait()
    sys.exit(0)
signal.signal(signal.SIGTERM, shutdown)
if os.environ.get("FAKE_UNAUTHORIZED"):
    print("HTTP status 401 Unauthorized", flush=True)
    sys.exit(2)
if os.environ.get("FAKE_EXIT"): sys.exit(2)
if os.environ.get("FAKE_DEVICE"):
    print("To grant access to the server, please log into https://github.com/login/device and use code TEST-CODE", flush=True)
    time.sleep(0.4)
if not os.environ.get("FAKE_TIMEOUT"):
    print("https://vscode.dev/tunnel/test", flush=True)
if os.environ.get("FAKE_IGNORE_TERM"): signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(1000)
''')
        self.code.chmod(0o700)
        self.session = VSCodeTunnel("test", self.root / "tunnel.log", str(self.code), self.root)

    def tearDown(self):
        self.session.stop(timeout=0.1)
        self.temp.cleanup()

    @patch.dict(os.environ, {"GH_TOKEN": "test-secret", "VSCODE_CLI_ACCESS_TOKEN": "wrong"})
    def test_ready_environment_reuse_shutdown_restart(self):
        self.assertIs(self.session.start(accept_license=True), self.session)
        pid = self.session.process.pid
        self.assertIn("inherited=True", self.session.logs())
        self.assertIn("vscode_pat=True", self.session.logs())
        self.assertEqual(self.session.start(accept_license=True).process.pid, pid)
        other = VSCodeTunnel("other")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            other.start(accept_license=True)
        # Independent interpreter must respect the filesystem lock as well.
        result = subprocess.run(["python", "-c",
            "from kaggle_vscode import VSCodeTunnel; VSCodeTunnel(code=" + repr(str(self.code)) + ").start(accept_license=True)"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime lock", result.stderr)
        self.session.stop()
        self.assertIsNone(self.session.process)
        self.assertIsNone(self.session.stop())
        with self.assertRaises(ProcessLookupError):
            os.killpg(pid, 0)
        self.session.start(accept_license=True)

    @patch.dict(os.environ, {"FAKE_TIMEOUT": "1"})
    def test_timeout_cleans_up(self):
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.session.start(timeout=0.3, accept_license=True)
        self.assertIsNone(self.session.process)

    @patch.dict(os.environ, {"FAKE_EXIT": "1"})
    def test_early_exit(self):
        with self.assertRaisesRegex(RuntimeError, "exited early"):
            self.session.start(accept_license=True)
        self.assertIsNone(self.session.process)

    @patch.dict(os.environ, {"FAKE_IGNORE_TERM": "1"})
    def test_forced_shutdown(self):
        self.session.start(accept_license=True)
        self.assertEqual(self.session.stop(timeout=0.1), -signal.SIGKILL)

    @patch.dict(os.environ, {"FAKE_DEVICE": "1"})
    def test_device_prompt_visible_and_auth_wait_separate(self):
        import contextlib
        import io
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.session.start(timeout=0.3, auth_timeout=3, accept_license=True)
        self.assertIn("TEST-CODE", output.getvalue())
        self.assertTrue(self.session.url)

    @patch.dict(os.environ, {"FAKE_LOGIN_FAIL": "1"})
    def test_explicit_token_login_failure_redacted(self):
        with self.assertRaises(RuntimeError) as error:
            self.session.start("tunnel-secret", accept_license=True)
        self.assertNotIn("tunnel-secret", str(error.exception))
        self.assertIsNone(self.session.process)
        self.assertIsNone(self.session._lock)

    def test_explicit_token_login_and_environment(self):
        self.session.start("tunnel-secret", accept_license=True)
        self.assertEqual(self.session._tunnel_token, "tunnel-secret")
        self.assertIn("vscode_pat=True", self.session.logs())

    @patch.dict(os.environ, {"FAKE_UNAUTHORIZED": "1"})
    def test_service_rejection_requires_device_reauthentication(self):
        # CLI login itself succeeds; the service later rejects the credential.
        with self.assertRaisesRegex(RuntimeError, "cached PAT") as error:
            self.session.start("tunnel-secret", accept_license=True)
        self.assertIn("tunnel user logout", str(error.exception))
        self.assertNotIn("tunnel-secret", str(error.exception))
        self.assertIsNone(self.session.process)
        self.assertIsNone(self.session._lock)

    def test_logs_redact_and_zero_lines(self):
        self.session.log_path.write_text("ghp_example123\nsecret-value\ntunnel-secret")
        self.session._token = "secret-value"
        self.session._tunnel_token = "tunnel-secret"
        self.assertNotIn("secret-value", self.session.logs())
        self.assertNotIn("tunnel-secret", self.session.logs())
        self.assertNotIn("ghp_example123", self.session.logs())
        self.assertEqual(self.session.logs(0), "")
