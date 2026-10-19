"""Install a checksum-verified standalone CLI without requiring root."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import tarfile
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen


def ensure_code(code="code", *, install=True):
    """Use an existing command or install Microsoft's current stable Linux CLI.

    Resolve stable to a commit and SHA-256 before downloading. Cache under the
    user's home and expose its bin directory on PATH for subsequent cells.
    Explicit custom executable paths never trigger an unrelated installation.
    """
    existing = shutil.which(code)
    if existing:
        return existing
    if not install or code != "code":
        raise RuntimeError(f"Missing {code}. Install the VS Code CLI or enable install_code=True.")
    if platform.system() != "Linux":
        raise RuntimeError("Automatic VS Code CLI installation requires Linux.")
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    if not arch:
        raise RuntimeError("Unsupported Linux architecture for automatic VS Code CLI installation.")
    target = Path.home() / ".cache" / "kaggle-vscode" / "bin"
    binary = target / "code"
    try:
        target.mkdir(parents=True, exist_ok=True)
        if not binary.is_file():
            with urlopen(f"https://update.code.visualstudio.com/api/update/cli-alpine-{arch}/stable/latest", timeout=30) as response:
                release = json.load(response)
            checksum = release["sha256hash"]
            commit = release["version"]
            url = release["url"]
            parsed = urlparse(url)
            if (not re.fullmatch(r"[0-9a-f]{64}", checksum)
                    or not re.fullmatch(r"[0-9a-f]{40}", commit)
                    or parsed.scheme != "https"
                    or parsed.hostname not in {"vscode.download.prss.microsoft.com", "download.visualstudio.microsoft.com"}):
                raise ValueError("Invalid official release metadata")
            with urlopen(url, timeout=60) as response:
                archive = response.read(100 * 1024 * 1024 + 1)
            if len(archive) > 100 * 1024 * 1024:
                raise ValueError("CLI archive exceeded size limit")
            if hashlib.sha256(archive).hexdigest() != checksum:
                raise ValueError("CLI archive checksum mismatch")
            # Extract just one regular file, never tar paths, links or devices.
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                members = [m for m in tar.getmembers() if m.name in {"code", "./code"} and m.isfile()]
                if len(members) != 1 or members[0].size > 100 * 1024 * 1024:
                    raise ValueError("CLI archive has no unique regular code binary")
                with tar.extractfile(members[0]) as source:
                    payload = source.read()
            fd, temporary = tempfile.mkstemp(prefix=".code-", dir=target)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(payload)
                os.chmod(temporary, 0o755)
                os.replace(temporary, binary)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            print(f"Installed VS Code CLI at {binary} (commit {commit}, SHA-256 verified).")
        os.environ["PATH"] = str(target) + os.pathsep + os.environ.get("PATH", "")
        return str(binary)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError):
        raise RuntimeError("Could not install the VS Code CLI. Check Internet access, home-directory permissions and official release availability; archive SHA-256 verification is required.") from None
