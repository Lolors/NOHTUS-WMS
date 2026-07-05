"""Backward-compatible wrapper.

The official application entrypoint is now nohtus.application.
This module remains only so older imports do not break immediately.
"""

from nohtus.application import main
