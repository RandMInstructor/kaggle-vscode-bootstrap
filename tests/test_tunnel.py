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
print("inherited=" + str(bool(os.environ.get("GH_TOKEN"))), flush=True)
print("vscode_pat=" + str("VSCODE_CLI_ACCESS_TOKEN" in os.environ), flush=True)
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1000)"])
print("child=" + str(child.pid), flush=True)
def shutdown(*args):
    child.terminate()
    child.wait()
    sys.exit(0)
signal.signal(signal.SIGTERM, shutdown)
if os.environ.get("FAKE_EXIT"): sys.exit(2)
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
        self.assertIn("vscode_pat=False", self.session.logs())
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

    def test_logs_redact_and_zero_lines(self):
        self.session.log_path.write_text("ghp_example123\nsecret-value")
        self.session._token = "secret-value"
        self.assertNotIn("secret-value", self.session.logs())
        self.assertNotIn("ghp_example123", self.session.logs())
        self.assertEqual(self.session.logs(0), "")
