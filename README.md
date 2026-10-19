# kaggle-vscode-bootstrap

Small, dependency-free Python helpers for **one Linux Kaggle notebook, one
GitHub account and one managed VS Code tunnel**. Python 3.10+.

## Prerequisites

Enable Internet in Kaggle notebook settings. In **Add-ons → Secrets**, add
`GITHUB_TOKEN` and grant this notebook access. Use a fine-grained GitHub PAT
with Contents read access to the private repositories you need; add write and
pull-request permissions only if your development work requires them.

Git and GitHub CLI (`gh`) must be on PATH. If `code` is missing, `setup_vscode`
automatically installs Microsoft's stable standalone CLI for Linux x64 or arm64.
The official release metadata resolves stable to a commit and SHA-256; the
download is verified before extracting only the regular `code` binary. It is
cached under `~/.cache/kaggle-vscode/bin`, which is added to notebook PATH.
No root access or write to `/usr/local/bin` is needed. Existing `code` commands
are reused; custom missing paths fail instead of downloading an unrelated CLI.
Use `install_code=False` to disable installation. Follow the official installation
instructions for [gh](https://github.com/cli/cli#installation) and manual
[VS Code CLI installation](https://code.visualstudio.com/docs/remote/tunnels#using-the-code-cli).
For a Kaggle image without gh, `!apt-get update -qq && apt-get install -y gh`
is one manual option. Record `gh --version`, `git --version` and `code --version`
when reproducing a notebook; upstream CLI changes can affect readiness detection.
The CLI must support `code tunnel --help` and `code tunnel user login`.

## Public bootstrap (recommended)

First cell (replace the tag with a full commit SHA for an immutable pin):

```python
%pip install --upgrade git+https://github.com/RandMInstructor/kaggle-vscode-bootstrap.git@v0.1.1
```

To develop this package itself in Kaggle, create its working checkout first:

```python
import subprocess
subprocess.run(["git", "clone", "--branch", "v0.1.1",
                "https://github.com/RandMInstructor/kaggle-vscode-bootstrap.git",
                "/kaggle/working/kaggle-vscode-bootstrap"], check=True)
```

For ongoing development, switch this checkout to `main` or a new feature branch
using `checkout_repo`; tags are detached release snapshots.

Review the [server license](https://aka.ms/vscode-server-license) before setting
`accept_license=True`. Configure and launch; when device sign-in is needed,
setup prints the link/code immediately and waits up to `auth_timeout=600`
seconds for you to complete it. The normal readiness timeout is 120 seconds.

```python
from kaggle_vscode import setup_vscode

session = setup_vscode(
    secret_name="GITHUB_TOKEN",
    tunnel_name="kaggle-gpu",
    repo="RandMInstructor/kaggle-vscode-bootstrap",  # or OWNER/private-project
    repo_dir="/kaggle/working/kaggle-vscode-bootstrap",
    branch="main",
    # create_branch=True,  # explicitly allow creating a missing branch
    # git_name="Your Name", git_email="YOUR_COMMIT_EMAIL",
    accept_license=True,
)
print(session.workspace)
print(session.url)  # emitted only after the CLI reports its vscode.dev URL
```

Open the URL, authenticate to VS Code as requested, then open `session.workspace`
in the connected editor. A URL is a readiness signal, not an end-to-end client
connection test. GitHub API success does not authenticate the tunnel.
Explicit `VSCODE_CLI_ACCESS_TOKEN` values are preserved. The package passes
them in the environment of `code tunnel user login --provider github` before
launching the tunnel, since this variable belongs to the CLI's login command.
To retrieve a tunnel credential from Kaggle Secrets, add
`tunnel_secret_name="VSCODE_TUNNEL_TOKEN"` to `setup_vscode` only for a credential
already verified against Microsoft's tunnel service. **Do not reuse your GitHub
PAT as the tunnel credential.** A successful CLI login may merely store the PAT;
the tunnel service can still reject it with HTTP 401. This is reported in
[VS Code issue #310726](https://github.com/microsoft/vscode/issues/310726).
A rejected tunnel token fails immediately
without displaying the token. With no tunnel token, cached VS Code sign-in or
the visible device flow is used. `VSCodeTunnel.start(token=...)` also supports
explicit environment-only token login. No token is added to command arguments.
The CLI manages its own sign-in storage; tunnel login may persist credentials
in its private CLI data directory. Do not publish that directory.

If you previously supplied a PAT to the tunnel, removing `tunnel_secret_name`
alone is insufficient because the CLI cached it. In the notebook, reset tunnel
sign-in and complete the displayed device flow:

```python
import os, shutil, subprocess
from pathlib import Path

os.environ.pop("VSCODE_CLI_ACCESS_TOKEN", None)
os.environ.pop("VSCODE_CLI_REFRESH_TOKEN", None)
code = shutil.which("code") or str(Path.home() / ".cache/kaggle-vscode/bin/code")
subprocess.run([code, "tunnel", "user", "logout"], check=True)
subprocess.run([code, "tunnel", "user", "login", "--provider", "github"], check=True)
```

Then rerun `setup_vscode(secret_name="GITHUB_TOKEN", accept_license=True)`
without `tunnel_secret_name`. This preserves GitHub PAT authentication for gh
and Git while the tunnel uses its separate device-authenticated session.

New server and terminal processes inherit `GH_TOKEN`. Open a **new** terminal:

```bash
gh api user --hostname github.com --jq .login
git clone https://github.com/OWNER/private-project.git
```

If a previous VS Code server reused an old environment, stop the session, end
the old server/runtime, rerun setup and reconnect. Never paste tokens into
VS Code settings. Do not print `os.environ`, enable shell tracing or publish
notebook outputs containing secrets. The token remains in process memory and
environment, not in package settings, Git URLs or command arguments.

```python
print(session.logs())
session.is_running()
session.stop(timeout=10)  # SIGTERM, bounded wait, group SIGKILL, clear handle
session.stop()            # safe repeated shutdown
session.restart(accept_license=True)
```

Repeated `setup_vscode` calls reuse the active session with matching name,
workspace, executable and credentials. Stop it before changing those values. A Linux
file lock prevents another package instance from silently starting a duplicate.
After notebook state loss, restart the Kaggle runtime: the package deliberately
does not recover or signal unverified PIDs from disk. An independently launched
`code tunnel` is outside this manager's ownership; stop it before using this API.

## Install a private package without credentials in URLs

This standalone first cell works without importing this bootstrap package.
Change `REPO` and `VERSION` to your private package and existing release tag or
commit. It fails with installation instructions when gh is missing. Use a fresh
destination for a different version; existing directories are never overwritten.

```python
import os, shutil, subprocess, sys
from pathlib import Path
from kaggle_secrets import UserSecretsClient

REPO = "OWNER/private-package"
VERSION = "v0.1.0"
destination = Path("/kaggle/working/bootstrap-private")
if not shutil.which("gh") or not shutil.which("git"):
    raise RuntimeError("Install Git and gh first: https://github.com/cli/cli#installation")
try:
    token = UserSecretsClient().get_secret("GITHUB_TOKEN")
except Exception:
    raise RuntimeError("Enable Internet and grant notebook access to GITHUB_TOKEN.") from None
if not isinstance(token, str) or not token.strip():
    raise RuntimeError("GITHUB_TOKEN is empty.")
env = dict(os.environ, GH_TOKEN=token.strip(), GH_PROMPT_DISABLED="1", GH_HOST="github.com")
def checked(args):
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError("Bootstrap command failed; check tools, version and repository access.")
try:
    if destination.exists():
        raise RuntimeError("Choose a fresh destination; this cell never overwrites a checkout.")
    checked(["gh", "api", "--hostname", "github.com", "user", "--jq", ".login"])
    checked(["gh", "auth", "setup-git", "--hostname", "github.com"])
    checked(["git", "clone", "--", f"https://github.com/{REPO}.git", str(destination)])
    checked(["git", "-C", str(destination), "checkout", "--detach", VERSION])
    checked([sys.executable, "-m", "pip", "install", str(destination)])
finally:
    env.pop("GH_TOKEN", None)
    del token
```

The second cell can call `setup_vscode` if that private package provides the
API, or install the public bootstrap above and use it alongside your package.
Git uses gh's credential helper and the explicit subprocess environment. There
is no token in pip's URL, Git's origin or the notebook source.

## API

* `authenticate_gh(token, setup_git=True)` validates GitHub API access, configures
  gh as Git's HTTPS credential helper, sets `GH_TOKEN`, reports and returns login.
* `checkout_repo(repo, destination=None, branch=None, create_branch=False,
  update=False)` returns an absolute `Path`. Existing destinations must have the
  matching HTTPS origin. Dirty branch changes/updates are refused. Missing
  remote branches are created only with explicit permission. Updates are
  opt-in and fast-forward only; there is no reset, clean or automatic merge.
* `VSCodeTunnel(name="kaggle-gpu", log_path=None, code="code", workspace=None)`
  supports `start(token=None, timeout=120, auth_timeout=600, accept_license=False)`, `restart`, `is_running`,
  `logs(lines=50)`, and `stop(timeout=10)`.
* `setup_vscode(...)` retrieves the named Kaggle secret lazily, authenticates,
  optionally checks out the repository, sets repository-local commit identity,
  and starts/reuses a session. `install_code=True` installs the CLI if missing;
  `tunnel_secret_name=None` optionally selects a separate tunnel credential.
  `auth_timeout=600` controls the device sign-in wait. `git_name`/`git_email` identify commits; they do
  not grant access. Use `code="/absolute/path/code"` for a standalone binary.

```python
from kaggle_vscode import checkout_repo
workspace = checkout_repo("OWNER/another-project", "/kaggle/working/another",
                          branch="feature/new-work", create_branch=True)
```

## Troubleshooting and validation

* Missing secret: confirm its spelling and notebook authorization; restart setup.
* gh operation failed: confirm Internet, PAT expiry, repository permissions and
  organization approval/SSO. Errors omit raw command output to avoid leaking PATs.
* Missing CLI: setup installs `code` automatically by default; install gh and
  Git manually. A desktop `code` wrapper may
  differ from the standalone CLI. Check `code tunnel --help`.
* Early exit / timeout: inspect `session.logs()` when available, or the sanitized
  error text. Device prompts now appear during setup, rather than only after
  timeout. Complete device sign-in, check name availability/network access,
  then retry. A failed startup stops the process it launched.
* Logs are local, mode 0600, and ignored by Git. Treat all raw CLI logs as private;
  `logs()` redacts the inherited PAT and common GitHub token formats.
* One runtime is ephemeral: Kaggle stop/restart ends the workspace and tunnel.
  Push your work explicitly before ending the notebook.

Development checks: `python -m pip install -e .`, then
`python -m unittest discover -s tests -v`. CI runs Python 3.10–3.13 on Linux,
including real process-group lifecycle tests and local Git checkout tests.

Live acceptance is a separate manual check: in a fresh Kaggle runtime install
the tag, authenticate a permitted private package clone, connect through the
tunnel, run `gh api user --jq .login` in a new terminal, rerun setup and confirm
the same PID, then stop and verify the process group is gone. Automated tests
do not claim to prove Kaggle connectivity or interactive VS Code sign-in.

## Releases

Use `@v0.1.1` or a full commit SHA in notebook pip URLs. Releases are GitHub
tags; no PyPI publication is required. Maintainers run tests, create an annotated
version tag and publish a GitHub release. Update package version and examples
together for later releases.

Official references: [gh authentication](https://cli.github.com/manual/gh_auth_login),
[Git credential setup](https://cli.github.com/manual/gh_auth_setup-git), and
[VS Code Remote Tunnels](https://code.visualstudio.com/docs/remote/tunnels).
