from srutils import shell_get_stdout_retcode

from . import paths
from .utils import is_func_symbol


def boundary_detection_funseeker(so_path):
    detect_cmd = f"{paths.funseeker_bin()} {so_path}"
    output, retcode = shell_get_stdout_retcode(detect_cmd)
    assert retcode == 0, f"FunSeeker failed with code {retcode}"
    checked_addrs = set()
    detected_entry_addrs = []
    for line in output.splitlines():
        if not line.startswith("FunctionEntry:"):
            continue
        addr = int(line.split(":")[1].strip(), 16)
        checked_addrs.add(addr)
        detected_entry_addrs.append(addr)

    # sort symbols by start address
    detected_entry_addrs.sort()
    return detected_entry_addrs


def boundary_detection_linear(elffile):
    symtab = elffile.get_section_by_name(".symtab")
    checked_addrs = set()
    detected_entry_addrs = []

    if symtab is not None:
        for symbol in symtab.iter_symbols():
            if symbol["st_value"] in checked_addrs:
                continue
            if is_func_symbol(symbol.entry["st_info"]["type"]):
                checked_addrs.add(symbol["st_value"])
                detected_entry_addrs.append(symbol["st_value"])

        return detected_entry_addrs

    # no .symtab section found, try to use .dynsym section
    dynsymtab = elffile.get_section_by_name(".dynsym")
    if dynsymtab is not None:
        for symbol in dynsymtab.iter_symbols():
            if symbol["st_value"] in checked_addrs:
                continue
            checked_addrs.add(symbol["st_value"])
            detected_entry_addrs.append(symbol["st_value"])
        return detected_entry_addrs

    return []


def boundary_detection_nucleus(so_path):
    # nucleus is a native module; import lazily so callers that never reach the
    # nucleus path do not require it at import time.
    import nucleus
    context = nucleus.load(so_path, binary_base=0x0)
    entry_addrs = []
    for function in context.cfg.functions:
        entry_addrs.append(function.start)
    return entry_addrs
