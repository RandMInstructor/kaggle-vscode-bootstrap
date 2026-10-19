"""One managed POSIX tunnel per notebook, with an advisory runtime lock."""
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
from .auth import require, run

_active = None


class VSCodeTunnel:
    def __init__(self, name="kaggle-gpu", log_path=None, code="code", workspace=None, *, environment=None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,19}", name):
            raise ValueError("Tunnel name must contain 1-20 letters, digits or hyphens.")
        self.name = name
        self.log_path = Path(log_path or Path(tempfile.gettempdir()) / f"kaggle-vscode-{os.getuid() if hasattr(os, 'getuid') else 'user'}.log")
        self.code = code
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.process = None
        self.url = None
        self._lock = None
        self._token = None
        self._tunnel_token = None
        self._environment = dict(environment) if environment is not None else {}

    def is_running(self):
        if self.process is None or self.process.returncode is not None:
            return False
        # Preserve the unreaped leader PID until stop() cleans its group.
        return os.waitid(os.P_PID, self.process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None

    def start(self, token=None, *, timeout=120, auth_timeout=600, accept_license=False):
        """Wait for readiness, displaying device sign-in or using a tunnel token.

        token is optional and specific to VS Code tunnel authentication. It is
        supplied only through the login subprocess environment, never argv.
        """
        global _active
        if os.name != "posix":
            raise RuntimeError("Tunnel management requires Linux/POSIX (run inside Kaggle).")
        if timeout <= 0 or auth_timeout <= 0:
            raise ValueError("timeout and auth_timeout must be positive.")
        if token is not None and (not isinstance(token, str) or not token.strip()):
            raise ValueError("Tunnel token must be a nonempty string.")
        if self.is_running():
            return self
        if _active is not None and _active is not self and _active.is_running():
            raise RuntimeError("A managed tunnel already exists; use setup_vscode() to reuse it.")
        if not accept_license:
            raise ValueError("Pass accept_license=True after reviewing the VS Code server license.")
        code = require(self.code)
        run([code, "tunnel", "--help"], timeout=30)
        if self.process is not None:
            self.stop()
        import fcntl
        lock_path = Path(tempfile.gettempdir()) / f"kaggle-vscode-{os.getuid()}.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self._lock = os.fdopen(fd, "w")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock.close()
            self._lock = None
            raise RuntimeError("Another managed tunnel holds the runtime lock. Stop it in its original notebook or restart the Kaggle session.") from None
        env = os.environ.copy()
        env.update(self._environment)
        if token is not None:
            env["VSCODE_CLI_ACCESS_TOKEN"] = token.strip()
        self._token = env.get("GH_TOKEN")
        self._tunnel_token = env.get("VSCODE_CLI_ACCESS_TOKEN")
        self.url = None
        try:
            if self._tunnel_token:
                # This environment variable belongs to LoginArgs, not serve args.
                run([code, "tunnel", "user", "login", "--provider", "github"], env=env, timeout=30)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as log:
                self.process = subprocess.Popen(
                    [code, "tunnel", "--accept-server-license-terms", "--name", self.name],
                    cwd=self.workspace, stdout=log, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, env=env, start_new_session=True)
            _active = self
            deadline = time.monotonic() + timeout
            device_prompt = None
            while time.monotonic() < deadline:
                if not self.is_running():
                    logs = self.logs()
                    if "401" in logs and ("Unauthorized" in logs or "unauthorized" in logs):
                        raise RuntimeError(
                            "Microsoft's tunnel service rejected the VS Code credential (401 Unauthorized). "
                            "GitHub CLI authentication does not establish tunnel access. "
                            "Remove VSCODE_CLI_ACCESS_TOKEN and VSCODE_CLI_REFRESH_TOKEN from the notebook environment, "
                            "run `code tunnel user logout`, then `code tunnel user login --provider github` "
                            "and complete device sign-in. Retry setup without tunnel_secret_name; keep secret_name for GitHub/Git. "
                            "A cached PAT can cause this even after tunnel_secret_name is removed. " + logs)
                    raise RuntimeError("VS Code tunnel exited early. " + logs)
                logs = self.logs(200)
                prompt = re.search(r"To grant access[^\n]*", logs)
                if prompt and prompt.group(0) != device_prompt:
                    device_prompt = prompt.group(0)
                    print(device_prompt, flush=True)
                    print("Complete VS Code device sign-in above; setup is waiting for tunnel readiness.", flush=True)
                    deadline = time.monotonic() + auth_timeout
                match = re.search(r"https://vscode\.dev/tunnel/[^\s\x1b]+", logs)
                if match:
                    self.url = match.group(0)
                    return self
                time.sleep(0.2)
            raise RuntimeError("Tunnel readiness timed out. Run `code tunnel user login --provider github` in a notebook cell, complete device sign-in, then retry. " + self.logs())
        except BaseException:
            self.stop()
            raise

    def _signal_group(self, sig):
        if self.process is None:
            return
        try:
            os.killpg(self.process.pid, sig)
        except ProcessLookupError:
            pass

    def stop(self, timeout=10):
        """Terminate the owned group; forget its PID after completed shutdown."""
        global _active
        if timeout < 0:
            raise ValueError("timeout must be nonnegative.")
        result = None
        if self.process is not None:
            # Never signal a PID already reaped by poll() or an earlier stop().
            if self.process.returncode is None:
                self._signal_group(signal.SIGTERM)
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    exited = os.waitid(os.P_PID, self.process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    if exited is not None:
                        break
                    time.sleep(0.05)
                # WNOWAIT reserves the leader PID until descendants are signaled.
                self._signal_group(signal.SIGKILL)
            result = self.process.wait(timeout=10)
            self.process = None
        self.url = None
        if self._lock is not None:
            self._lock.close()
            self._lock = None
        if _active is self:
            _active = None
        return result

    def restart(self, **kwargs):
        self.stop()
        return self.start(**kwargs)

    def logs(self, lines=50):
        if lines < 0:
            raise ValueError("lines must be nonnegative.")
        if not self.log_path.exists() or lines == 0:
            return ""
        text = "\n".join(self.log_path.read_text(errors="replace").splitlines()[-lines:])
        for token in (self._token, self._tunnel_token):
            if token:
                text = text.replace(token, "[REDACTED]")
        return re.sub(r"(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)", "[REDACTED]", text)
