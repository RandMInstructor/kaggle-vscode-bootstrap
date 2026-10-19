"""Conservative HTTPS repository checkout."""
from pathlib import Path
import os
import re
from .auth import require, run


def checkout_repo(repo, destination=None, branch=None, create_branch=False, update=False, *, environment=None):
    """Clone OWNER/REPO or reuse its checkout without resetting local work."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or any(x in {".", ".."} for x in repo.split("/")):
        raise ValueError("repo must be OWNER/REPO, without a URL or credentials.")
    git = require("git")
    if environment is not None:
        env = os.environ.copy()
        env.update(environment)
        environment = env
    path = Path(destination or repo.split("/")[1]).expanduser().resolve()
    url = f"https://github.com/{repo.removesuffix('.git')}.git"

    def command(*args):
        return run([git, *args], cwd=path, env=environment)

    if branch:
        # Validate before clone or fetch; '--' is not accepted by every branch command.
        run([git, "check-ref-format", "--branch", branch], env=environment)
        if branch.startswith("-") or branch == "HEAD":
            raise ValueError("Invalid branch name.")
    if path.exists():
        if not (path / ".git").exists():
            raise RuntimeError("Destination exists but is not a checkout.")
        origin = command("remote", "get-url", "origin")
        if origin.lower().removesuffix(".git") != url.lower().removesuffix(".git"):
            raise RuntimeError("Destination origin does not match the requested HTTPS repository.")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        run([git, "clone", "--", url, str(path)], timeout=300, env=environment)
    if branch and command("branch", "--show-current") != branch:
        if command("status", "--porcelain"):
            raise RuntimeError("Commit or stash local changes before switching branches.")
        refs = command("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin").splitlines()
        if f"refs/heads/{branch}" in refs:
            command("switch", branch)
        else:
            command("fetch", "origin")
            refs = command("for-each-ref", "--format=%(refname)", "refs/remotes/origin").splitlines()
            if f"refs/remotes/origin/{branch}" in refs:
                command("switch", "--track", "-c", branch, f"origin/{branch}")
            elif create_branch:
                command("switch", "-c", branch)
            else:
                raise RuntimeError("Branch missing. Use create_branch=True to create it.")
    if update:
        if command("status", "--porcelain"):
            raise RuntimeError("Commit or stash local changes before updating.")
        command("pull", "--ff-only")
    return path
