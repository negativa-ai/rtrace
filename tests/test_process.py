from types import SimpleNamespace

import pytest

import rtrace.process
from rtrace.process import deduplicate_modules, get_loaded_module


class TestDeduplicateModules:
    def test_removes_duplicate_paths(self):
        modules = [
            SimpleNamespace(path="/lib/a.so"),
            SimpleNamespace(path="/lib/b.so"),
            SimpleNamespace(path="/lib/a.so"),
        ]

        result = deduplicate_modules(modules)

        assert [m.path for m in result] == ["/lib/a.so", "/lib/b.so"]

    def test_keeps_first_occurrence(self):
        first = SimpleNamespace(path="/lib/a.so", marker="first")
        second = SimpleNamespace(path="/lib/a.so", marker="second")

        result = deduplicate_modules([first, second])

        assert result == [first]

    def test_empty(self):
        assert deduplicate_modules([]) == []


class _StubModule:
    """Stands in for Module so tests do not construct a full Library."""

    def __init__(self, path, start, end, **kwargs):
        self.path = path
        self.start = start
        self.end = end


@pytest.fixture
def stub_module(monkeypatch):
    monkeypatch.setattr(rtrace.process, "Module", _StubModule)


def _write_modules_log(directory, pid, tid, lines):
    path = directory / f"rtrace-intermediate-{pid}-{tid}-loaded_modules.log"
    path.write_text("".join(f"{line}\n" for line in lines))


class TestGetLoadedModule:
    def test_reads_modules_for_pid_tid(self, tmp_path, stub_module):
        _write_modules_log(
            tmp_path, 100, 200, ["/lib/a.so : 4096 : 8192", "/lib/b.so : 8192 : 12288"]
        )

        modules = get_loaded_module(100, [200], str(tmp_path))

        assert [(m.path, m.start, m.end) for m in modules] == [
            ("/lib/a.so", 4096, 8192),
            ("/lib/b.so", 8192, 12288),
        ]

    def test_deduplicates_across_tids(self, tmp_path, stub_module):
        _write_modules_log(tmp_path, 100, 200, ["/lib/a.so : 4096 : 8192"])
        _write_modules_log(tmp_path, 100, 201, ["/lib/a.so : 4096 : 8192"])

        modules = get_loaded_module(100, [200, 201], str(tmp_path))

        assert len(modules) == 1

    def test_falls_back_to_other_pids(self, tmp_path, stub_module):
        # the requested pid-tid file is empty; another pid has modules
        _write_modules_log(tmp_path, 100, 200, [])
        _write_modules_log(tmp_path, 999, 888, ["/lib/a.so : 4096 : 8192"])

        modules = get_loaded_module(100, [200], str(tmp_path))

        assert [m.path for m in modules] == ["/lib/a.so"]

    def test_raises_when_all_module_logs_are_empty(self, tmp_path, stub_module):
        _write_modules_log(tmp_path, 100, 200, [])

        with pytest.raises(ValueError, match="At least one pid-tid file should exist"):
            get_loaded_module(100, [200], str(tmp_path))

    def test_missing_log_file_raises(self, tmp_path, stub_module):
        with pytest.raises(FileNotFoundError):
            get_loaded_module(100, [200], str(tmp_path))

    def test_rejects_malformed_line(self, tmp_path, stub_module):
        _write_modules_log(tmp_path, 100, 200, ["/lib/a.so : 4096"])

        with pytest.raises(AssertionError, match="Invalid line format"):
            get_loaded_module(100, [200], str(tmp_path))
