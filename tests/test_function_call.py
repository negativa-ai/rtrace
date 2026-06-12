from types import SimpleNamespace

import pytest

from rtrace.function_call import BlockInfo, Call, CallLogProcessor


class TestCall:
    def test_repr(self):
        call = Call("foo", 0x1234, 0x34, "/lib/x.so", 2)

        assert repr(call) == "Call(name=foo, abs_addr=4660, so_path=/lib/x.so)"


class TestLogLineParsers:
    def test_entry(self):
        assert CallLogProcessor.is_entry("Entry: 4096")
        assert not CallLogProcessor.is_entry("Exit: 4096")
        assert CallLogProcessor.get_entry_address("Entry: 4096") == 4096

    def test_exit(self):
        assert CallLogProcessor.is_exit("Exit: 4096")
        assert not CallLogProcessor.is_exit("Entry: 4096")
        assert CallLogProcessor.get_exit_address("Exit: 4096") == 4096

    def test_arg(self):
        assert CallLogProcessor.is_arg("Arg_0: 7")
        assert not CallLogProcessor.is_arg("Ret: 7")
        assert CallLogProcessor.get_arg("Arg_1: 7") == 7

    def test_ret(self):
        assert CallLogProcessor.is_ret("Ret: 42")
        assert not CallLogProcessor.is_ret("Entry: 42")
        assert CallLogProcessor.get_ret("Ret: 42") == 42

    def test_block(self):
        assert CallLogProcessor.is_block("BB: 4096")
        assert not CallLogProcessor.is_block("Entry: 4096")
        assert CallLogProcessor.get_block("BB: 4096") == 4096


class TestBlockInfo:
    def _write_log(self, directory, pid, tid, lines):
        path = directory / f"rtrace-intermediate-{pid}-{tid}-block_info.log"
        path.write_text("".join(f"{line}\n" for line in lines))

    def test_parses_blocks(self, tmp_path):
        self._write_log(tmp_path, 100, 200, ["4096 : 5", "8192 : 3"])

        info = BlockInfo(100, [200], str(tmp_path))

        assert info.get_block_size(4096) == 5
        assert info.get_block_size(8192) == 3

    def test_duplicate_address_same_count_is_fine(self, tmp_path):
        self._write_log(tmp_path, 100, 200, ["4096 : 5", "4096 : 5"])

        info = BlockInfo(100, [200], str(tmp_path))

        assert info.get_block_size(4096) == 5

    def test_duplicate_address_different_count_rejected(self, tmp_path):
        self._write_log(tmp_path, 100, 200, ["4096 : 5", "4096 : 6"])

        with pytest.raises(AssertionError, match="Duplicate block address"):
            BlockInfo(100, [200], str(tmp_path))

    def test_merges_multiple_tids(self, tmp_path):
        self._write_log(tmp_path, 100, 200, ["4096 : 5"])
        self._write_log(tmp_path, 100, 201, ["8192 : 3"])

        info = BlockInfo(100, [200, 201], str(tmp_path))

        assert info.get_block_size(4096) == 5
        assert info.get_block_size(8192) == 3


class _StubModule:
    def __init__(self, start, end, path, functions):
        self.start = start
        self.end = end
        self.path = path
        self._functions = functions

    def get_function_at_address(self, address):
        for func in self._functions:
            if func.start <= address - self.start < func.end:
                return func
        return None


class _StubProcessMemory:
    def __init__(self, modules):
        self.modules = modules

    def get_module_at_address(self, address):
        for module in self.modules:
            if module.start <= address < module.end:
                return module
        return None


def make_processor(raw_logs, process_memory, block_info):
    """Build a CallLogProcessor without reading log files from disk."""
    processor = object.__new__(CallLogProcessor)
    processor.process_memory = process_memory
    processor.raw_logs = raw_logs
    processor.abs_addr_to_func = {}
    processor.root_call = Call("root", 0, 0, "root", 0)
    processor.block_info = block_info
    return processor


class TestProcessLogs:
    def test_builds_call_tree_with_args_ret_and_blocks(self):
        func = SimpleNamespace(name="foo", start=0x34, end=0x100, so_path="/lib/a.so", num_args=2)
        module = _StubModule(start=0x1000, end=0x2000, path="/lib/a.so", functions=[func])
        process_memory = _StubProcessMemory([module])
        raw_logs = [
            "Entry: 4148",  # 0x1034 = module base + func start
            "Arg_0: 1",
            "Arg_1: 2",
            "BB: 4148",
            "Ret: 42",
            "Exit: 4148",
        ]

        processor = make_processor(raw_logs, process_memory, block_info={4148: 5})
        processor.process_logs()

        assert len(processor.root_call.calls) == 1
        call = processor.root_call.calls[0]
        assert call.name == "foo"
        assert call.so_path == "/lib/a.so"
        assert call.args == [1, 2]
        assert call.ret_val == 42
        assert call.executed_blocks == 1
        assert call.executed_insts == 5

    def test_nested_calls(self):
        outer = SimpleNamespace(name="outer", start=0x34, end=0x40, so_path="/lib/a.so", num_args=0)
        inner = SimpleNamespace(name="inner", start=0x40, end=0x50, so_path="/lib/a.so", num_args=0)
        module = _StubModule(start=0x1000, end=0x2000, path="/lib/a.so", functions=[outer, inner])
        process_memory = _StubProcessMemory([module])
        raw_logs = [
            "Entry: 4148",  # outer
            "Entry: 4160",  # inner
            "Exit: 4160",
            "Exit: 4148",
        ]

        processor = make_processor(raw_logs, process_memory, block_info={})
        processor.process_logs()

        assert [c.name for c in processor.root_call.calls] == ["outer"]
        assert [c.name for c in processor.root_call.calls[0].calls] == ["inner"]

    def test_unknown_address_becomes_unknown_call(self):
        process_memory = _StubProcessMemory([])
        raw_logs = ["Entry: 4148", "Exit: 4148"]

        processor = make_processor(raw_logs, process_memory, block_info={})
        processor.process_logs()

        assert processor.root_call.calls[0].name == "unknown"
