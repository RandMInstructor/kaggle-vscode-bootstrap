"""Notebook setup orchestration."""
import os
from pathlib import Path
from .auth import authenticate_gh, require, run
from .repo import checkout_repo
from . import tunnel


def setup_vscode(secret_name="GITHUB_TOKEN", tunnel_name="kaggle-gpu", *,
                 repo=None, repo_dir=None, branch=None, create_branch=False,
                 update=False, git_name=None, git_email=None, code="code",
                 timeout=120, accept_license=False):
    """Authenticate, prepare a workspace, then launch or reuse one tunnel."""
    if os.name != "posix":
        raise RuntimeError("Run setup_vscode inside a Linux Kaggle notebook.")
    if not accept_license:
        raise ValueError("Review https://aka.ms/vscode-server-license then pass accept_license=True.")
    for executable in ("gh", "git", code):
        require(executable)
    active = tunnel._active
    if not repo and any((branch, create_branch, update, git_name, git_email)):
        raise ValueError("Repository options require repo=OWNER/REPO.")
    workspace = Path(repo_dir or (repo.split("/")[-1] if repo else Path.cwd())).resolve()
    if active is not None and active.is_running():
        if active.name != tunnel_name or active.workspace != workspace or active.code != code:
            raise RuntimeError("Stop the current session before changing tunnel configuration.")
    try:
        from kaggle_secrets import UserSecretsClient
        token = UserSecretsClient().get_secret(secret_name)
    except Exception:
        raise RuntimeError("Could not retrieve Kaggle secret. Check the secret name, notebook access and Internet setting.") from None
    authenticate_gh(token)
    if active is not None and active.is_running() and active._token != os.environ["GH_TOKEN"]:
        raise RuntimeError("GitHub token changed. Stop and rerun setup so the tunnel inherits it.")
    if repo:
        workspace = checkout_repo(repo, repo_dir, branch, create_branch, update)
        for key, value in (("user.name", git_name), ("user.email", git_email)):
            if value is not None:
                run(["git", "config", "--local", key, value], cwd=workspace)
    if active is not None and active.is_running():
        return active
    session = tunnel.VSCodeTunnel(tunnel_name, code=code, workspace=workspace)
    return session.start(timeout=timeout, accept_license=accept_license)
