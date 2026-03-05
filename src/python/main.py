#!/home/ubuntu/miniconda3/envs/rtrace/bin/python

import argparse
import logging
import json
import os
import sys
import struct

import numpy as np
from elftools.elf.elffile import ELFFile
from srutils import shell_system

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--logdir', type=str,
                        help="Directory to store output files")
    parser.add_argument('cmd', nargs="*", help="Command to run")
    parser.add_argument("--filter", action='store_true')
    parser.add_argument("--calllog", action='store_true')
    parser.add_argument("--mode",  type=int, default=0, choices=[0, 1],
                        help="0 for rich mode, 1 for light mode")
    parser.add_argument("--so_name", type=str, default=None, help="Shared object name to filter the calllog.")
    args = parser.parse_args()
    log_dir = args.logdir
    cmd = " ".join(args.cmd)
    filter = args.filter
    calllog = args.calllog
    mode = args.mode

    trace_cmd = f'/home/ubuntu/repos/rtrace/submodules/dynamorio/build/bin64/drrun  -c /home/ubuntu/repos/rtrace/src/build/librtrace.so --log_dir {log_dir} --mode {mode} -- {cmd}'

    retcode = shell_system(trace_cmd)
    print(f"Trace command executed: {trace_cmd}")

    base_post_process_cmd = f'/home/ubuntu/repos/rtrace/src/python/postprocess.py --input {log_dir}/ --output {log_dir} --mode {mode} --so_name {args.so_name}'

    if filter:
        base_post_process_cmd += " --filter"
    if calllog:
        base_post_process_cmd += " --calllog"
    shell_system(base_post_process_cmd)
    sys.exit(retcode)
