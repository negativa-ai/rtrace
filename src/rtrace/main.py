import argparse
import logging
import subprocess
import sys

from . import paths
from .edition import MODE_NAMES, require_mode_supported

logger = logging.getLogger(__name__)

LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def main():
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    parser = argparse.ArgumentParser(prog="rtrace")
    parser.add_argument("--logdir", type=str, help="Directory to store output files")
    parser.add_argument("cmd", nargs="*", help="Command to run")
    parser.add_argument("--calllog", action="store_true")
    parser.add_argument(
        "--mode",
        choices=list(MODE_NAMES),
        default="rich",
        help="rich for full prototype analysis, light for lightweight tracing",
    )
    parser.add_argument(
        "--so_name", type=str, default=None, help="Shared object name to filter the calllog."
    )
    args = parser.parse_args()

    # The native client takes an integer mode; resolve the human-readable name once.
    mode = MODE_NAMES[args.mode]

    # Light edition supports light mode only; fail early with guidance.
    require_mode_supported(mode)

    log_dir = args.logdir

    # -quiet: the bundle ships only the 64-bit release DynamoRIO libraries, and
    # drrun's install-completeness check warns about the absent lib32/debug
    # variants on every run otherwise.
    #
    # --cache_dir / --python let the native client run boundary detection in rich
    # mode (it runs `python -m rtrace.preprocess`) without any hardcoded paths.
    # Built as an argument list and run without a shell, so command names and the
    # traced program's arguments need no quoting/escaping.
    trace_argv = [
        str(paths.drrun()),
        "-quiet",
        "-c",
        str(paths.librtrace_so()),
        "--log_dir",
        log_dir,
        "--mode",
        str(mode),
        "--cache_dir",
        str(paths.cache_dir().resolve()),
        "--python",
        sys.executable,
        "--",
        *args.cmd,
    ]
    retcode = subprocess.run(trace_argv).returncode
    logger.info("Trace command executed: %s", " ".join(trace_argv))

    post_process_argv = [
        sys.executable,
        "-m",
        "rtrace.postprocess",
        "--input",
        f"{log_dir}/",
        "--output",
        log_dir,
        "--mode",
        args.mode,
    ]
    if args.so_name is not None:
        post_process_argv += ["--so_names", args.so_name]
    if args.calllog:
        post_process_argv += ["--calllog"]
    subprocess.run(post_process_argv)
    sys.exit(retcode)


if __name__ == "__main__":
    main()
