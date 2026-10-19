"""Environment-only GitHub authentication."""
import os
import shutil
import subprocess


def require(executable):
    path = shutil.which(executable)
    if not path:
        raise RuntimeError(f"Missing {executable}. Install it and add it to PATH; see README prerequisites.")
    return path


def run(command, *, env=None, cwd=None, timeout=60):
    # Never surface subprocess output: third-party failures may echo credentials.
    try:
        return subprocess.run(command, env=env, cwd=cwd, timeout=timeout,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError(f"{command[0]} operation failed. Check installation, Internet access, permissions and arguments.") from None


def authenticate_gh(token, setup_git=True):
    """Validate a PAT, configure HTTPS credentials and return the GitHub login."""
    if not isinstance(token, str) or not token.strip():
        raise ValueError("A nonempty GitHub token is required.")
    gh = require("gh")
    if setup_git:
        require("git")
    env = os.environ.copy()
    env.update(GH_TOKEN=token.strip(), GH_PROMPT_DISABLED="1", GH_HOST="github.com")
    login = run([gh, "api", "--hostname", "github.com", "user", "--jq", ".login"], env=env, timeout=30)
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login):
        raise RuntimeError("GitHub authentication returned an invalid login.")
    if setup_git:
        run([gh, "auth", "setup-git", "--hostname", "github.com"], env=env, timeout=30)
    os.environ.update(GH_TOKEN=env["GH_TOKEN"], GH_PROMPT_DISABLED="1", GH_HOST="github.com")
    print(f"GitHub CLI authenticated as {login}.")
    return login
