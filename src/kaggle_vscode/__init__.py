"""Kaggle bootstrap helpers. No Kaggle dependency is imported at module load."""
from .auth import authenticate_gh
from .repo import checkout_repo
from .setup import setup_vscode
from .tunnel import VSCodeTunnel

__version__ = "0.1.1"
__all__ = ["authenticate_gh", "checkout_repo", "VSCodeTunnel", "setup_vscode"]
