import json

import pandas as pd

from .process import ProcessMemory


class Call(object):
    def __init__(self, name, abs_addr, relative_addr, so_path, num_args):
        self.name = name
        self.abs_addr = abs_addr
        self.relative_addr = relative_addr
        self.so_path = so_path
        self.num_args = num_args
        self.args = []
        self.ret_val = None
        self.calls = []
        self.executed_blocks = 0
        self.executed_insts = 0

    def add_arg(self, arg):
        self.args.append(arg)

    def add_call(self, call):
        self.calls.append(call)

    def set_ret_val(self, ret_val):
        self.ret_val = ret_val

    def __repr__(self):
        return f"Call(name={self.name}, abs_addr={self.abs_addr}, so_path={self.so_path})"


class BlockInfo(object):
    def __init__(self, pid, tids, log_dir):
        self.pid = pid
        self.tids = tids
        self.log_dir = log_dir
        self.block_info = {}
        for tid in tids:
            with open(f'{log_dir}/rtrace-intermediate-{pid}-{tid}-block_info.log', 'r') as f:
                for line in f:
                    parts = line.split(":")
                    assert len(parts) == 2, f"Invalid block info line: {line}"
                    addr = int(parts[0].strip())
                    num_insts = int(parts[1].strip())
                    if addr in self.block_info:
                        assert self.block_info[
                            addr] == num_insts, f"Duplicate block address {addr} with different instruction counts: {self.block_info[addr]} vs {num_insts}"
                    else:
                        self.block_info[addr] = num_insts

    def get_block_size(self, abs_addr):
        """Get the number of instructions in a block at the given absolute address."""
        return self.block_info[abs_addr]


class CallLogProcessor(object):
    def __init__(self, process_memory: ProcessMemory, block_info: BlockInfo, pid, tid, log_dir, so_names=None):
        self.process_memory = process_memory
        self.log_path = log_dir
        self.raw_logs = []
        self.abs_addr_to_func = {}
        self.root_call = Call("root", 0, 0, "root", 0,)
        self.block_info = block_info.block_info
        with open(f'{log_dir}/rtrace-intermediate-{pid}-{tid}-func_args_ret.log', 'r') as f:
            if so_names is None:
                for line in f:
                    self.raw_logs.append(line.strip())
            else:
                so_names=so_names.split(",")
                so_names= set([so_name.strip() for so_name in so_names])
                for line in f:
                    if self.is_entry(line) or self.is_exit(line):
                        addr = self.get_entry_address(line) if self.is_entry(line) else self.get_exit_address(line)
                        module = self.process_memory.get_module_at_address(addr)
                        if module is not None:
                            for so_name in so_names:
                                if so_name in module.path:
                                    self.raw_logs.append(line.strip())
                                    break
        print(len(self.raw_logs), "function call logs loaded from", f'{log_dir}/rtrace-intermediate-{pid}-{tid}-func_args_ret.log')
    def _create_call(self, abs_address):
        func = None
        if abs_address in self.abs_addr_to_func:
            func = self.abs_addr_to_func[abs_address]
        else:
            module = self.process_memory.get_module_at_address(abs_address)
            if module:
                func = module.get_function_at_address(abs_address)
                self.abs_addr_to_func[abs_address] = func
        if func is None:
            return Call("unknown", abs_address, 0, "unknown", 0)
        return Call(func.name, abs_address, func.start, func.so_path, func.num_args)

    def process_logs(self):
        stack = [self.root_call]
        total_calls = 0
        unmatch_entry_exit = 0
        total_blocks = 0
        unmatch_func_block = 0
        for log in self.raw_logs:
            if CallLogProcessor.is_entry(log):
                total_calls += 1
                addr = CallLogProcessor.get_entry_address(log)
                call = self._create_call(addr)
                stack[-1].add_call(call)
                stack.append(call)
            elif CallLogProcessor.is_arg(log):
                arg = CallLogProcessor.get_arg(log)
                stack[-1].add_arg(arg)
            elif CallLogProcessor.is_block(log):
                total_blocks += 1
                addr = CallLogProcessor.get_block(log)
                if addr not in self.block_info or \
                        self.process_memory.get_module_at_address(addr) is None or \
                        self.process_memory.get_module_at_address(addr).get_function_at_address(addr) is None or \
                        self.process_memory.get_module_at_address(addr).get_function_at_address(addr).start != stack[-1].relative_addr:  # the block does not belong to the current function
                    # this might due to exception handling
                    unmatch_func_block += 1
                else:  # only count the blocks belong to the current function
                    stack[-1].executed_blocks += 1
                    stack[-1].executed_insts += self.block_info[addr]
            elif CallLogProcessor.is_ret(log):
                ret_val = CallLogProcessor.get_ret(log)
                stack[-1].set_ret_val(ret_val)
            elif CallLogProcessor.is_exit(log):
                addr = CallLogProcessor.get_exit_address(log)
                call = stack.pop()
                if call.abs_addr != addr:
                    # should not happend but it happens with some exit:0, might due to exception handling
                    unmatch_entry_exit += 1
        print(
            f"Unmatched entry/exit: {unmatch_entry_exit}/{total_calls}; final stack depth: {len(stack)}")

        print(f"Unmatched function block: {unmatch_func_block}/{total_blocks}")

    def dump(self, output_path):
        overview = []

        def serialize_call(cur_call):
            call_json = {
                "name": cur_call.name,
                "start_addr": hex(cur_call.relative_addr),
                "so_path": cur_call.so_path,
                "num_args": cur_call.num_args,
                "args": cur_call.args,
                "ret_val": cur_call.ret_val,
                "executed_blocks": cur_call.executed_blocks,
                "executed_insts": cur_call.executed_insts,
                "calls": [serialize_call(c) for c in cur_call.calls]
            }
            overview.append({
                "so_path": cur_call.so_path,
                "name": cur_call.name,
                "start_addr": hex(cur_call.relative_addr),
                "num_calls": len(cur_call.calls),
                "executed_blocks": cur_call.executed_blocks,
                "executed_insts": cur_call.executed_insts
            })
            return call_json
        call_json = serialize_call(self.root_call)
        with open(output_path, 'w') as f:
            json.dump(call_json, f, indent=4)
        pd.DataFrame(overview).to_csv(
            output_path.replace('.json', '.csv'), index=False)

    @staticmethod
    def is_entry(line):
        return line.startswith("Entry:")

    @staticmethod
    def get_entry_address(line):
        return int(line.split(":")[1].strip())

    @staticmethod
    def is_exit(line):
        return line.startswith("Exit:")

    @staticmethod
    def get_exit_address(line):
        return int(line.split(":")[1].strip())

    @staticmethod
    def is_arg(line):
        return line.startswith("Arg_")

    @staticmethod
    def get_arg(line):
        return int(line.split(":")[1].strip())

    @staticmethod
    def is_ret(line):
        return line.startswith("Ret:")

    @staticmethod
    def get_ret(line):
        return int(line.split(":")[1].strip())

    @staticmethod
    def is_block(line):
        return line.startswith("BB:")

    @staticmethod
    def get_block(line):
        return int(line.split(":")[1].strip())
