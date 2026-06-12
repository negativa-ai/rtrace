import argparse
import json
import os

from . import paths
from .function_call import BlockInfo, CallLogProcessor
from .library import Instruction
from .process import ProcessMemory


FUNCTION_INFO_DIR = str(paths.cache_dir())


class Node(object):
    def __init__(self, address, base, so_name="", section_name="", insn: Instruction = None, is_function_start=False, func_start=None, func_end=None):
        self._insn = insn
        self.so_name = so_name
        self.section_name = section_name
        self.address = address
        self.ins = []
        self.outs = []
        self.inds = []
        self.base = base
        # whether this node is a function start identified at preprocessing time (FunSeeker)
        self.is_function_start = is_function_start
        self.func_start = func_start
        self.func_end = func_end

    def is_jmp(self):
        if self._insn is None:
            return False
        return self._insn.is_jmp()

    def is_call(self):
        if self._insn is None:
            return False
        return self._insn.is_call()

    def is_endbr(self):
        if self._insn is None:
            return False
        return self._insn.is_endbr()

    def is_ret(self):
        if self._insn is None:
            return False
        return self._insn.is_ret()

    def is_indirect_call(self):
        if self._insn is None:
            return False
        return self._insn.is_indirect_call()

    def is_indirect_jmp(self):
        if self._insn is None:
            return False
        return self._insn.is_indirect_jmp()

    def is_in_plt(self):
        return "plt" in self.section_name

    def is_potential_indirect_return_endbr(self):
        if self._insn is None:
            return False
        if self.is_in_plt():
            return False

        if not self._insn.is_potential_indirect_return_endbr():
            return False

        indirect_jmp_exist = False
        for income in self.ins:
            # any call/jmp-from-plt indicates this is a function instead of indrect return
            if income.is_call() or income.is_in_plt():
                return False
            # at least one income must be indirect call/jmp or ret
            if income.is_indirect_call() or income.is_indirect_jmp() or income.is_ret():
                indirect_jmp_exist = True

        return indirect_jmp_exist

    def get_potential_leading_call(self):
        assert self.is_potential_indirect_return_endbr(
        ), "Node is not a potential indirect return endbr"
        insn = self._insn.get_potential_leading_call()
        return insn

    def __repr__(self):
        return f"{self.so_name}: {hex(self.address)}, {self.is_function_start}, {self.section_name}, {self.base}"

    def __hash__(self):
        return hash(f"{self.so_name}:{hex(self.address)}")

    def __eq__(self, other):
        if not isinstance(other, Node):
            return False
        return (self.so_name == other.so_name and
                self.address == other.address)


def _create_node_from_address(address, ind, process_memory):
    module = process_memory.get_module_at_address(address)
    if module is None:
        node = Node(address=address, base=0, is_function_start=False)
    else:
        insn = module.get_instruction_at_address(address)
        is_function_start = module.is_function_start(
            address, is_relative_addr=False)
        func = module.get_function_at_address(address)
        if func is not None:
            node = Node(address=insn.address, base=module.start,
                        so_name=module.path, section_name=insn.section_name, insn=insn, is_function_start=is_function_start, func_start=func.start, func_end=func.end)
        else:
            node = Node(address=insn.address, base=module.start,
                        so_name=module.path, section_name=insn.section_name, insn=insn, is_function_start=is_function_start)
    node.inds.append(ind)
    return node


def create_cfg(branch_taken, process_memory, thread_id):
    cur_node = _create_node_from_address(branch_taken[0], 0, process_memory)
    address_to_node = {branch_taken[0]: cur_node}
    edges = []
    for ind in range(1, len(branch_taken)):
        b = branch_taken[ind]
        if b not in address_to_node:
            node = _create_node_from_address(b, ind, process_memory)
            address_to_node[b] = node
        else:
            node = address_to_node[b]
        cur_node.outs.append(node)
        node.ins.append(cur_node)
        node.inds.append(ind)
        edges.append((cur_node, node))
        cur_node = node
    entry_node = address_to_node[branch_taken[0]]
    return entry_node, address_to_node, edges


def identify_false_positives(address_to_node, branch_taken):
    identified_false_positives = set()
    for _, node in address_to_node.items():
        if node.is_potential_indirect_return_endbr():
            for ind in node.inds:
                cur_address = node.address+node.base
                assert cur_address == branch_taken[ind]
                # find another node that has the same address before the current one
                for j in range(ind-1, -1, -1):
                    if branch_taken[j] == cur_address:
                        j = j+1
                        break
                assert j >= 0
                examined_addresses = set(branch_taken[j+1:ind])
                # get potential leading call address
                potential_leading_insn = node.get_potential_leading_call()
                potential_leading_call_addr = potential_leading_insn.address + node.base

                # check if the potential leading call address is in the
                if potential_leading_call_addr in examined_addresses:
                    identified_false_positives.add(node)

    sorted_false_positives = sorted(
        list(identified_false_positives), key=lambda x: x.so_name)
    return sorted_false_positives


def identify_false_negatives(address_to_node, branch_taken):
    fns = set()
    for i, b in enumerate(branch_taken):
        node = address_to_node[b]
        if node and node.so_name == "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2" and node.address == 0x56d5:
            fb = branch_taken[i+2]
            fn_node = address_to_node[fb]
            if fn_node.is_in_plt():
                continue
            fns.add(fn_node)
    return list(fns)


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
        report[so_path].append({
            "function_name": func.name,
            "start_offset": func.start
        })
    with open(output_path, "w") as f:
        json.dump(report, f, indent=4)


def remove_duplicate_branch_taken(branch_taken):
    """
    rtrace can report duplicate addresses, for eaxample, an address is a target but the same time it is also a branch instruction, then it will appear twice in the branch_taken list. We need to remove the consequtive duplicate addresses.
    0x1 jmp 0x2
    0x2 jmp 0x3
    Then 0x2 will appear twice in the branch_taken list.
    """
    if not branch_taken:
        return branch_taken
    new_branch_taken = [branch_taken[0]]
    for i in range(1, len(branch_taken)):
        if branch_taken[i] != branch_taken[i-1]:
            new_branch_taken.append(branch_taken[i])
    return new_branch_taken


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


def get_branch_taken(pid, tid, input_dir):
    file_path = f"{input_dir}/rtrace-intermediate-{pid}-{tid}-branch_taken.log"
    with open(file_path, "r") as f:
        branch_taken = []
        for line in f:
            address = int(line.strip())
            branch_taken.append(address)
        return branch_taken


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
    parser = argparse.ArgumentParser(
        description="Postprocess script for rtrace.")
    parser.add_argument("--input", type=str, required=True,
                        help="Input file for postprocessing.")
    parser.add_argument("--output", type=str, required=True,
                        help="Output dir for postprocessing results.")
    parser.add_argument("--filter", action='store_true')
    parser.add_argument("--calllog", action='store_true')
    parser.add_argument("--mode", type=int, default=0, choices=[0, 1, 2],
                        help="0 for heavy mode, 1 for light mode, 2 for light mode with removal")
    parser.add_argument("--bd_algo", type=str, default=None, help="Boundary detaction algorithm, linear or funseeker")
    parser.add_argument("--bd_cache_dir",type=str, default=FUNCTION_INFO_DIR,
                        help="Cache directory for boundary detection")
    parser.add_argument("--so_names", type=str, default=None, help="Shared object names to filter the calllog, liba,lib,libc")
    args = parser.parse_args()
    input_dir = args.input
    output_dir = args.output
    filter = args.filter
    calllog = args.calllog
    mode = args.mode
    bd_algo = args.bd_algo
    bd_cache_dir = args.bd_cache_dir
    so_names = args.so_names

    all_fps = []
    all_fns = []
    process_memory_cache = {}
    module_cache = {}
    pid_to_tids = get_pid_tid(input_dir)
    for pid, tids in pid_to_tids.items():
        process_memory = ProcessMemory(pid, tids, input_dir, mode=mode, bd_algo=bd_algo, bd_cache_dir=bd_cache_dir, analyze_function_prototypes=(mode == 0))
        process_memory_cache[pid] = process_memory
        for m in process_memory.modules:
            module_cache[m.path] = m
        for tid in tids:
            if mode == 0:
                print(f"Processing PID: {pid}, TID: {tid}")
                branch_taken = get_branch_taken(pid, tid, input_dir)
                branch_taken = remove_duplicate_branch_taken(branch_taken)
                entry_node, addr_to_node, edges = create_cfg(
                    branch_taken, process_memory, tid)
                fps = identify_false_positives(addr_to_node, branch_taken)
                all_fps.extend(fps)
                fns = identify_false_negatives(addr_to_node, branch_taken)
                all_fns.extend(fns)

    if filter:
        for node in all_fps:
            module = module_cache[node.so_name]
            print(f"remove function {node.so_name}: {hex(node.address)}")
            module.remove_function_at_address(
                node.address, is_relative_addr=True)
        for node in all_fns:
            module = module_cache[node.so_name]
            print(f"Insert function {node.so_name}: {hex(node.address)}")
            module.insert_function_at_address(node.address,
                                              is_relative_addr=True)
    if calllog:
        for pid, tids in pid_to_tids.items():
            process_memory = process_memory_cache[pid]
            block_info = BlockInfo(pid, tids, input_dir)
            for tid in tids:
                call_processor = CallLogProcessor(
                    process_memory, block_info, pid, tid, input_dir, so_names=so_names)
                call_processor.process_logs()
                output_path = f'{output_dir}/function-calls-{pid}-{tid}.json'
                call_processor.dump(output_path)

    for pid, tids in pid_to_tids.items():
        process_memory = process_memory_cache[pid]
        for tid in tids:
            print(f"Processing {pid}, {tid}")
            trapped_insns = get_executed_instrumentations(pid, tid, input_dir)
            output_file_path = f"{output_dir}/function-executed-{pid}-{tid}.json"
            trapped_insns_to_func_coverage_report(
                trapped_insns, process_memory, output_file_path)
