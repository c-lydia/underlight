"""Locate the policy shared with Underlight launchers, including source checkouts."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflows.privacy import check_export, check_ollama, mode
