import argparse
import sys

from srutils import shell_system

from . import paths
from .edition import require_mode_supported


def main():
    parser = argparse.ArgumentParser(prog="rtrace")
    parser.add_argument("--logdir", type=str, help="Directory to store output files")
    parser.add_argument("cmd", nargs="*", help="Command to run")
    parser.add_argument("--filter", action="store_true")
    parser.add_argument("--calllog", action="store_true")
    parser.add_argument(
        "--mode", type=int, default=0, choices=[0, 1], help="0 for rich mode, 1 for light mode"
    )
    parser.add_argument(
        "--so_name", type=str, default=None, help="Shared object name to filter the calllog."
    )
    args = parser.parse_args()

    # Light edition supports mode 1 only; fail early with guidance.
    require_mode_supported(args.mode)

    log_dir = args.logdir
    cmd = " ".join(args.cmd)

    # -quiet: the bundle ships only the 64-bit release DynamoRIO libraries, and
    # drrun's install-completeness check warns about the absent lib32/debug
    # variants on every run otherwise.
    trace_cmd = (
        f"{paths.drrun()} -quiet -c {paths.librtrace_so()} "
        f"--log_dir {log_dir} --mode {args.mode} -- {cmd}"
    )
    retcode = shell_system(trace_cmd)
    print(f"Trace command executed: {trace_cmd}")

    post_process_cmd = (
        f"{sys.executable} -m rtrace.postprocess "
        f"--input {log_dir}/ --output {log_dir} --mode {args.mode}"
    )
    if args.so_name is not None:
        post_process_cmd += f" --so_names {args.so_name}"
    if args.filter:
        post_process_cmd += " --filter"
    if args.calllog:
        post_process_cmd += " --calllog"
    shell_system(post_process_cmd)
    sys.exit(retcode)


if __name__ == "__main__":
    main()
