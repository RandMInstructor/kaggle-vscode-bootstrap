"""Notebook setup orchestration."""
import os
from pathlib import Path
from .auth import authenticate_gh, require, run
from .repo import checkout_repo
from .install import ensure_code
from . import tunnel


def setup_vscode(secret_name="GITHUB_TOKEN", tunnel_name="kaggle-gpu", *,
                 repo=None, repo_dir=None, branch=None, create_branch=False,
                 update=False, git_name=None, git_email=None, code="code",
                 timeout=120, accept_license=False, install_code=True,
                 tunnel_secret_name=None, auth_timeout=600, environment=None):
    """Authenticate, prepare a workspace, then launch or reuse one tunnel."""
    if os.name != "posix":
        raise RuntimeError("Run setup_vscode inside a Linux Kaggle notebook.")
    if not accept_license:
        raise ValueError("Review https://aka.ms/vscode-server-license then pass accept_license=True.")
    for executable in ("gh", "git"):
        require(executable)
    code = ensure_code(code, install=install_code)
    active = tunnel._active
    if not repo and any((branch, create_branch, update, git_name, git_email)):
        raise ValueError("Repository options require repo=OWNER/REPO.")
    workspace = Path(repo_dir or (repo.split("/")[-1] if repo else Path.cwd())).resolve()
    if active is not None and active.is_running():
        if active.name != tunnel_name or active.workspace != workspace or active.code != code:
            raise RuntimeError("Stop the current session before changing tunnel configuration.")
    try:
        from kaggle_secrets import UserSecretsClient
        secrets = UserSecretsClient()
        token = secrets.get_secret(secret_name)
        tunnel_token = secrets.get_secret(tunnel_secret_name) if tunnel_secret_name else None
    except Exception:
        raise RuntimeError("Could not retrieve Kaggle secret. Check the secret name, notebook access and Internet setting.") from None
    if not isinstance(token, str) or not token.strip():
        raise ValueError("The GitHub secret must contain a nonempty token.")
    if tunnel_secret_name and (not isinstance(tunnel_token, str) or not tunnel_token.strip()):
        raise ValueError("The tunnel secret must contain a nonempty token.")
    env = os.environ.copy()
    if environment is not None:
        env.update(environment)
    env.update(GH_TOKEN=token.strip(), GH_PROMPT_DISABLED="1", GH_HOST="github.com")
    if tunnel_token is not None:
        tunnel_token = tunnel_token.strip()
        env["VSCODE_CLI_ACCESS_TOKEN"] = tunnel_token
    if active is not None and active.is_running() and (
            active._token != env["GH_TOKEN"] or
            active._tunnel_token != env.get("VSCODE_CLI_ACCESS_TOKEN")):
        raise RuntimeError("Authentication credentials changed. Stop and rerun setup so the tunnel inherits them.")
    authenticate_gh(environment=env)
    if repo:
        workspace = checkout_repo(repo, repo_dir, branch, create_branch, update, environment=env)
        for key, value in (("user.name", git_name), ("user.email", git_email)):
            if value is not None:
                run(["git", "config", "--local", key, value], cwd=workspace, env=env)
    if active is not None and active.is_running():
        return active
    session = tunnel.VSCodeTunnel(tunnel_name, code=code, workspace=workspace, environment=env)
    return session.start(token=tunnel_token, timeout=timeout,
                         auth_timeout=auth_timeout, accept_license=accept_license)
