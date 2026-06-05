"""Edition gating.

RTrace ships in two editions that differ only in their Python dependencies:

* ``light`` -- supports ``--mode 1`` only.
* ``heavy`` -- supports both ``--mode 0`` and ``--mode 1``; adds ``angr`` (plus
  ``capstone`` and ``networkx``) for the mode-0 prototype/CFG analysis.

The edition is detected at runtime by the presence of the ``angr`` dependency,
which is installed only in the heavy edition. ``find_spec`` checks availability
without paying the cost of importing ``angr``.
"""
import importlib.util
import sys

# True when the heavy-only dependencies are installed.
SUPPORTS_HEAVY_MODE = importlib.util.find_spec("angr") is not None


def require_mode_supported(mode):
    """Exit with a helpful message if ``mode`` is unsupported by this edition."""
    if mode == 0 and not SUPPORTS_HEAVY_MODE:
        sys.exit(
            "rtrace: mode 0 (rich/heavy mode) requires the heavy edition.\n"
            "        This is the light edition, which supports --mode 1 only.\n"
            "        Install the heavy edition: pip install 'rtrace[heavy]'\n"
            "        (or download the rtrace-heavy bundle)."
        )
