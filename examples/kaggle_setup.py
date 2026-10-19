"""Run after public package install and separate VS Code device sign-in."""
from kaggle_vscode import setup_vscode

session = setup_vscode(
    secret_name="GITHUB_TOKEN",
    tunnel_name="kaggle-gpu",
    repo="RandMInstructor/kaggle-vscode-bootstrap",
    repo_dir="/kaggle/working/kaggle-vscode-bootstrap",
    branch="main",
    accept_license=True,  # Review https://aka.ms/vscode-server-license first.
)
print(session.workspace)
print(session.url)
print(session.logs())
# Later: session.stop()
