import logging
import os

from .library import Library

logger = logging.getLogger(__name__)


class Module(object):
    """Module represents a loaded library in the process memory."""

    def __init__(
        self,
        path,
        start,
        end,
        mode=0,
        bd_algo=None,
        bd_cache_dir=None,
        analyze_function_prototypes=False,
    ):
        self.path = path
        self.start = start
        self.end = end
        self.lib = Library(
            path,
            boundary_detection_method=bd_algo,
            func_info_dir=bd_cache_dir,
            analyze_function_prototypes=analyze_function_prototypes,
        )
        if mode == 0:
            self.lib.decode()

    def is_in(self, addr):
        return self.start <= addr < self.end

    def get_instruction_at_address(self, address):
        """Get instruction at a specific address within the module."""
        addr_in_module = address - self.start
        return self.lib.get_instruction_at_address(addr_in_module)

    def get_function_at_address(self, address):
        """Get function at a specific address within the module."""
        addr_in_module = address - self.start
        return self.lib.get_function_at_address(addr_in_module)

    def remove_function_at_address(self, address, is_relative_addr=True):
        """Remove function at a specific address within the module."""
        if is_relative_addr:
            addr_in_module = address
        else:
            addr_in_module = address - self.start
        return self.lib.remove_function_at_address(addr_in_module)

    def insert_function_at_address(self, address, is_relative_addr=True):
        """Insert function at a specific address within the module."""
        if is_relative_addr:
            addr_in_module = address
        else:
            addr_in_module = address - self.start
        return self.lib.insert_function_at_address(addr_in_module)

    def is_function_start(self, address, is_relative_addr=True):
        """Check if the address is the start of a function within the module."""
        if is_relative_addr:
            addr_in_module = address
        else:
            addr_in_module = address - self.start

        return self.lib.is_function_start(addr_in_module)


def deduplicate_modules(modules):
    """Drop modules with an already-seen path, keeping the first occurrence."""
    module_path_set = set()
    dep_modules = []
    for m in modules:
        if m.path in module_path_set:
            continue
        dep_modules.append(m)
        module_path_set.add(m.path)
    return dep_modules


def get_loaded_module(
    pid, tids, input_dir, mode=0, bd_algo=None, bd_cache_dir=None, analyze_function_prototypes=False
):
    # first try to read the corresponding pid-tid file,
    # if it is empty, try to read another pid-tid' file
    def read_module_info(file_path):
        with open(file_path, "r") as f:
            lines = f.readlines()
            if len(lines) == 0:
                return None
            modules = []
            for line in lines:
                parts = line.strip().split(":")
                if len(parts) != 3:
                    raise ValueError(f"Invalid line format: {line.strip()!r} in {file_path}")
                so_path = parts[0].strip()
                start = int(parts[1].strip())
                end = int(parts[2].strip())
                if "libtorch_cuda.so" in so_path and bd_algo == "funseeker":
                    logger.warning(
                        "libtorch_cuda.so is skipped for funseeker mode, "
                        "as it is too large (>=2GB)."
                    )
                    # skip libtorch_cuda.so
                    continue
                modules.append(
                    Module(
                        so_path,
                        start,
                        end,
                        mode=mode,
                        bd_algo=bd_algo,
                        bd_cache_dir=bd_cache_dir,
                        analyze_function_prototypes=analyze_function_prototypes,
                    )
                )
            return modules

    all_modules = []
    for tid in tids:
        file_path = f"{input_dir}/rtrace-intermediate-{pid}-{tid}-loaded_modules.log"
        modules = read_module_info(file_path)
        if modules is not None:
            all_modules.extend(modules)
    if len(all_modules) > 0:
        return deduplicate_modules(all_modules)

    logger.warning("cannot find loaded modules for %s-%s, trying to read other pids", pid, tids)
    # cannot find loaded modules for current pid, try with other pids
    for f in os.listdir(input_dir):
        if f.startswith("rtrace-intermediate") and f.endswith("-loaded_modules.log"):
            modules = read_module_info(f"{input_dir}/{f}")
            if modules is not None:
                all_modules.extend(modules)
    if len(all_modules) > 0:
        return deduplicate_modules(all_modules)
    raise ValueError(
        f"At least one pid-tid file should exist, but not found for pid: {pid}, tid: {tid}"
    )


class ProcessMemory(object):
    def __init__(
        self,
        pid,
        tids,
        log_dir,
        mode=0,
        bd_algo=None,
        bd_cache_dir=None,
        analyze_function_prototypes=False,
    ):
        self.pid = pid
        self.tids = tids
        self.log_dir = log_dir
        self.modules = get_loaded_module(
            pid,
            tids,
            log_dir,
            mode=mode,
            bd_algo=bd_algo,
            bd_cache_dir=bd_cache_dir,
            analyze_function_prototypes=analyze_function_prototypes,
        )

    def get_module_at_address(self, address):
        for module in self.modules:
            if module.is_in(address):
                return module
        return None
