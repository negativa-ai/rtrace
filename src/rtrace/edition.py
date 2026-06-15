"""Edition gating and the human-readable ``--mode`` mapping.

RTrace ships in two editions that differ only in their Python dependencies:

* ``light`` -- supports ``--mode light`` only.
* ``heavy`` -- supports both ``--mode rich`` and ``--mode light``; adds ``angr``
  for the rich-mode prototype analysis.

The edition is detected at runtime by the presence of the ``angr`` dependency,
which is installed only in the heavy edition. ``find_spec`` checks availability
without paying the cost of importing ``angr``.
"""

import importlib.util
import sys

# Human-readable mode names mapped to the integer the native client expects.
# ``rich`` = full prototype analysis (heavy edition); ``light`` = lightweight.
MODE_RICH = 0
MODE_LIGHT = 1
MODE_NAMES = {"rich": MODE_RICH, "light": MODE_LIGHT}

# True when the heavy-only dependencies are installed.
SUPPORTS_HEAVY_MODE = importlib.util.find_spec("angr") is not None


def require_mode_supported(mode):
    """Exit with a helpful message if ``mode`` is unsupported by this edition.

    ``mode`` is the resolved integer (see ``MODE_NAMES``).
    """
    if mode == MODE_RICH and not SUPPORTS_HEAVY_MODE:
        sys.exit(
            "rtrace: --mode rich requires the heavy edition.\n"
            "        This is the light edition, which supports --mode light only.\n"
            "        Install the heavy edition: pip install 'rtrace[heavy]'\n"
            "        (or download the rtrace-heavy bundle)."
        )
