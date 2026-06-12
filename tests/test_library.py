import pytest

from rtrace.library import Function, Library


def make_library(functions):
    """Build a Library around a synthetic function list, skipping ELF parsing."""
    lib = object.__new__(Library)
    lib.so_path = "/lib/test.so"
    lib._functions = sorted(functions, key=lambda f: f.start)
    return lib


@pytest.fixture
def library():
    # two adjacent functions, then a gap, then a third
    return make_library(
        [
            Function(0x100, 0x200, "f1", "/lib/test.so"),
            Function(0x200, 0x300, "f2", "/lib/test.so"),
            Function(0x400, 0x500, "f3", "/lib/test.so"),
        ]
    )


class TestGetFunctionAtAddress:
    def test_start_address(self, library):
        assert library.get_function_at_address(0x100).name == "f1"

    def test_address_within_range(self, library):
        assert library.get_function_at_address(0x2FF).name == "f2"

    def test_before_first_function(self, library):
        assert library.get_function_at_address(0x50) is None

    def test_in_gap_between_functions(self, library):
        assert library.get_function_at_address(0x350) is None

    def test_past_last_function(self, library):
        assert library.get_function_at_address(0x500) is None


class TestIsFunctionStart:
    def test_exact_start(self, library):
        assert library.is_function_start(0x200)

    def test_mid_function(self, library):
        assert not library.is_function_start(0x250)

    def test_unmapped(self, library):
        assert not library.is_function_start(0x50)


class TestInsertFunctionAtAddress:
    def test_split_existing_function(self, library):
        assert library.insert_function_at_address(0x250)

        assert library.get_function_at_address(0x240).name == "f2"
        assert library.get_function_at_address(0x240).end == 0x250
        inserted = library.get_function_at_address(0x250)
        assert inserted.name == "post_detected"
        assert (inserted.start, inserted.end) == (0x250, 0x300)

    def test_existing_start_is_rejected(self, library):
        assert not library.insert_function_at_address(0x200)

    def test_insert_before_first_function(self, library):
        assert library.insert_function_at_address(0x50)

        inserted = library.get_function_at_address(0x50)
        assert (inserted.start, inserted.end) == (0x50, 0x100)

    def test_insert_in_gap_raises(self, library):
        with pytest.raises(ValueError, match="no suitable position found"):
            library.insert_function_at_address(0x350)


class TestRemoveFunctionAtAddress:
    def test_remove_middle_function_extends_previous(self, library):
        assert library.remove_function_at_address(0x200)

        # f2's range is absorbed by f1
        assert library.get_function_at_address(0x250).name == "f1"
        assert library.get_function_at_address(0x250).end == 0x300

    def test_remove_first_function_extends_next(self, library):
        assert library.remove_function_at_address(0x100)

        assert library.get_function_at_address(0x150).name == "f2"
        assert library.get_function_at_address(0x150).start == 0x100

    def test_non_start_address_is_rejected(self, library):
        assert not library.remove_function_at_address(0x150)
        assert library.get_function_at_address(0x150).name == "f1"

    def test_unmapped_address_is_rejected(self, library):
        assert not library.remove_function_at_address(0x350)
