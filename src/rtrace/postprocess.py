import argparse
import json
import logging
import os

from . import paths
from .edition import MODE_NAMES, MODE_RICH
from .function_call import BlockInfo, CallLogProcessor
from .process import ProcessMemory

logger = logging.getLogger(__name__)

FUNCTION_INFO_DIR = str(paths.cache_dir())


def trapped_insns_to_func_coverage_report(trapped_insns, process_memory, output_path):
    report = {}
    trapped_insns = set(trapped_insns)
    for addr in trapped_insns:
        module = process_memory.get_module_at_address(addr)
        if module is None:
            continue
        func = module.get_function_at_address(addr)
        if func is None:
            # the instruction might be in plt
            continue
        so_path = module.path
        if so_path not in report:
            report[so_path] = []
        report[so_path].append({"function_name": func.name, "start_offset": func.start})
    with open(output_path, "w") as f:
        json.dump(report, f, indent=4)


def get_pid_tid(input_dir):
    pid_to_tids = {}
    for file in os.listdir(input_dir):
        if file.startswith("rtrace-intermediate-"):
            parts = file.split("-")
            pid = parts[2].strip()
            tid = parts[3].strip()
            if pid not in pid_to_tids:
                pid_to_tids[pid] = []
            if tid not in pid_to_tids[pid]:
                pid_to_tids[pid].append(tid)
    return pid_to_tids


def get_executed_instrumentations(pid, tid, input_dir):
    file_path = f"{input_dir}/rtrace-intermediate-{pid}-{tid}-executed_instrumentations.log"
    with open(file_path, "r") as f:
        executed_insns = []
        for line in f:
            address = int(line.strip())
            executed_insns.append(address)
        return executed_insns


def get_func_arg_ret(pid, tid, input_dir):
    file_path = f"{input_dir}/rtrace-intermediate-{pid}-{tid}-func_args_ret.log"
    with open(file_path, "r") as f:
        func_args_ret = []
        for line in f:
            func_args_ret.append(line.strip())
    return func_args_ret


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Postprocess script for rtrace.")
    parser.add_argument("--input", type=str, required=True, help="Input file for postprocessing.")
    parser.add_argument(
        "--output", type=str, required=True, help="Output dir for postprocessing results."
    )
    parser.add_argument("--calllog", action="store_true")
    parser.add_argument(
        "--mode",
        choices=list(MODE_NAMES),
        default="rich",
        help="rich for full prototype analysis, light for lightweight tracing",
    )
    parser.add_argument(
        "--bd_algo",
        type=str,
        default=None,
        help="Boundary detaction algorithm, linear or funseeker",
    )
    parser.add_argument(
        "--bd_cache_dir",
        type=str,
        default=FUNCTION_INFO_DIR,
        help="Cache directory for boundary detection",
    )
    parser.add_argument(
        "--so_names",
        type=str,
        default=None,
        help="Shared object names to filter the calllog, liba,lib,libc",
    )
    args = parser.parse_args()
    input_dir = args.input
    output_dir = args.output
    calllog = args.calllog
    mode = MODE_NAMES[args.mode]
    bd_algo = args.bd_algo
    bd_cache_dir = args.bd_cache_dir
    so_names = args.so_names

    process_memory_cache = {}
    pid_to_tids = get_pid_tid(input_dir)
    for pid, tids in pid_to_tids.items():
        process_memory = ProcessMemory(
            pid,
            tids,
            input_dir,
            bd_algo=bd_algo,
            bd_cache_dir=bd_cache_dir,
            analyze_function_prototypes=(mode == MODE_RICH),
        )
        process_memory_cache[pid] = process_memory

    if calllog:
        for pid, tids in pid_to_tids.items():
            process_memory = process_memory_cache[pid]
            block_info = BlockInfo(pid, tids, input_dir)
            for tid in tids:
                call_processor = CallLogProcessor(
                    process_memory, block_info, pid, tid, input_dir, so_names=so_names
                )
                call_processor.process_logs()
                output_path = f"{output_dir}/function-calls-{pid}-{tid}.json"
                call_processor.dump(output_path)

    for pid, tids in pid_to_tids.items():
        process_memory = process_memory_cache[pid]
        for tid in tids:
            logger.info("Processing %s, %s", pid, tid)
            trapped_insns = get_executed_instrumentations(pid, tid, input_dir)
            output_file_path = f"{output_dir}/function-executed-{pid}-{tid}.json"
            trapped_insns_to_func_coverage_report(trapped_insns, process_memory, output_file_path)
