import json
import logging
import os
import struct

from elftools.elf.elffile import ELFFile, SymbolTableSection

from . import paths

# capstone is a heavy-edition (mode 0) dependency. It is only referenced by the
# Instruction class methods, which run exclusively in mode 0, so guard the import
# to let the light edition load this module without capstone installed.
try:
    from capstone import CS_GRP_CALL, CS_GRP_JUMP, CS_GRP_RET
    from capstone.x86_const import (
        X86_INS_ENDBR32,
        X86_INS_ENDBR64,
        X86_INS_NOP,
        X86_OP_MEM,
        X86_OP_REG,
    )
except ImportError:
    pass

from .boundary_detection import (
    boundary_detection_funseeker,
    boundary_detection_linear,
    boundary_detection_nucleus,
)
from .disassembler import disassemble_data
from .utils import is_func_symbol

logger = logging.getLogger(__name__)


class Instruction(object):
    def __init__(self, insn, section_name=None, next=None, so_path=None):
        self.insn = insn  # original instruction object from capstone
        self.section_name = section_name
        self.address = insn.address
        self.next = next
        self.prev = None
        self.so_path = so_path  # path to the shared object file, if applicable

    def __repr__(self):
        return (
            f"{self.so_path}:{self.section_name}:{hex(self.address)} "
            f"{self.insn.mnemonic} {self.insn.op_str}"
        )

    def is_endbr(self):
        return self.insn.id in (X86_INS_ENDBR64, X86_INS_ENDBR32)

    def is_call(self):
        return CS_GRP_CALL in self.insn.groups

    def is_jmp(self):
        return CS_GRP_JUMP in self.insn.groups

    def is_nop(self):
        return self.insn.id == X86_INS_NOP

    def is_ret(self):
        return CS_GRP_RET in self.insn.groups

    def is_indirect_call(self):
        is_call = CS_GRP_CALL in self.insn.groups
        if is_call:
            op = self.insn.operands[0]
            return op.type in (X86_OP_MEM, X86_OP_REG)
        else:
            return False

    def is_indirect_jmp(self):
        is_jmp = CS_GRP_JUMP in self.insn.groups
        if is_jmp:
            op = self.insn.operands[0]
            return op.type in (X86_OP_MEM, X86_OP_REG)
        else:
            return False


class Function(object):
    def __init__(self, start, end, name, so_path):
        self.start = start
        self.end = end
        self.name = name
        self.so_path = so_path
        self.num_args = -1  # number of arguments, -1 means unknown
        self.args_size = []  # size of each argument
        self.ret_size = -1  # return size, -1 means unknown


class Library(object):
    INIT_FINI_SEC_NAMES = [".init_array", ".fini_array"]

    def __init__(
        self,
        so_path,
        analyze_function_prototypes=False,
        func_info_dir=None,
        boundary_detection_method=None,
        debug_sym_file=None,
    ):
        if func_info_dir is None:
            func_info_dir = str(paths.cache_dir())
        self.so_path = so_path
        # pyelftools reads sections lazily, so the underlying file must stay
        # open for the lifetime of the Library; call close() when done.
        self._file = open(so_path, "rb")
        self._elffile = ELFFile(self._file)
        self._instructions = []
        self._addr_to_instruction = {}
        self._functions = []
        self.boundary_detection_method = boundary_detection_method
        self.debug_sym_file = debug_sym_file
        # unlike _get_function_ind_at_address (range lookup), this maps the
        # exact start address to the function object
        self._addr_to_function = {}
        self.function_info_path = f"{func_info_dir}/{os.path.basename(so_path)}.info"
        if os.path.exists(self.function_info_path):
            with open(self.function_info_path, "r") as f:
                funcs = json.load(f)
            for f in funcs:
                func = Function(f["start"], f["end"], f["name"], self.so_path)
                func.num_args = f.get("num_args", 0)
                func.args_size = f.get("args_size", [])
                func.ret_size = f.get("ret_size", 0)
                self._functions.append(func)
        else:
            self._create_functions()
            self._set_func_names()
            if analyze_function_prototypes:
                self._set_function_prototype()
            if not os.path.exists(func_info_dir):
                os.makedirs(func_info_dir)
            if not os.path.exists(self.function_info_path):
                with open(self.function_info_path, "w") as output_file:
                    function_json_data = []
                    for f in self._functions:
                        function_json_data.append(
                            {
                                "start": f.start,
                                "end": f.end,
                                "name": f.name,
                                "num_args": f.num_args,
                                "args_size": f.args_size,
                                "ret_size": f.ret_size,
                            }
                        )
                    json.dump(function_json_data, output_file, indent=4)
        self._functions.sort(key=lambda f: f.start)

    def close(self):
        """Close the underlying ELF file handle."""
        self._file.close()

    def _list_executable_sections(self):
        sections = []
        for section in self._elffile.iter_sections():
            if section["sh_flags"] & 0x4:
                sections.append(section.name)
        return sections

    def _has_symtab(self):
        return self._elffile.get_section_by_name(".symtab") is not None

    def _cet_enabled(self):
        # Check if IBT is enabled by looking for .note.gnu.property section
        note_section = self._elffile.get_section_by_name(".note.gnu.property")
        if note_section is None:
            return False
        for note in note_section.iter_notes():
            if note["n_desc"][0]["pr_data"] == 3:
                return True
        return False

    def _function_boundary_detection(self):
        # If method is specified, use it
        # if not specified, use linear if symtab available, otherwise funseeker detection
        if self.boundary_detection_method is None:
            if self._has_symtab():
                logger.info("Using linear boundary detection for %s", self.so_path)
                entry_addrs = boundary_detection_linear(self._elffile)
            elif self._cet_enabled():
                logger.info("Using Funseeker for function boundary detection: %s", self.so_path)
                entry_addrs = boundary_detection_funseeker(self.so_path)
            else:
                logger.info("Using Nucleus for function boundary detection: %s", self.so_path)
                entry_addrs = boundary_detection_nucleus(self.so_path)
        elif self.boundary_detection_method == "linear":
            if self.debug_sym_file is not None:
                logger.info(
                    "Using linear boundary detection for %s, %s",
                    self.so_path,
                    self.debug_sym_file,
                )
                with open(self.debug_sym_file, "rb") as f:
                    entry_addrs = boundary_detection_linear(ELFFile(f))
            else:
                logger.info("Using linear boundary detection for %s", self.so_path)
                entry_addrs = boundary_detection_linear(self._elffile)
                logger.info("%d functions detected", len(entry_addrs))
        elif self.boundary_detection_method == "funseeker":
            logger.info("Using Funseeker for function boundary detection: %s", self.so_path)
            entry_addrs = boundary_detection_funseeker(self.so_path)
        elif self.boundary_detection_method == "nucleus":
            logger.info("Using Nucleus for function boundary detection: %s", self.so_path)
            entry_addrs = boundary_detection_nucleus(self.so_path)
        else:
            raise ValueError(
                f"Unknown method for boundary detection: {self.boundary_detection_method}"
            )
        entry_addrs = sorted(set(entry_addrs))  # remove duplicates and sort
        return entry_addrs

    def _read_init_fini_array(self):
        pointers = []
        for section_name in Library.INIT_FINI_SEC_NAMES:
            section = self._elffile.get_section_by_name(section_name)
            if not section:
                continue
            data = section.data()
            addr_size = 8 if self._elffile.elfclass == 64 else 4
            fmt = "<Q" if self._elffile.little_endian else ">Q"  # Q = uint64
            if self._elffile.elfclass == 32:
                fmt = "<I" if self._elffile.little_endian else ">I"  # I = uint32
            for i in range(0, len(data), addr_size):
                ptr_bytes = data[i : i + addr_size]
                ptr = struct.unpack(fmt, ptr_bytes)[0]
                pointers.append(ptr)
        return pointers

    def _get_symbols(self):
        func_start_to_name = {}

        def set_symbols(sec):
            if not isinstance(sec, SymbolTableSection):
                return
            for symbol in sec.iter_symbols():
                start_addr = symbol["st_value"]
                if not is_func_symbol(symbol.entry["st_info"]["type"]):
                    continue
                if symbol.entry["st_info"]["type"] != "STT_FUNC":
                    continue
                if start_addr not in func_start_to_name:
                    func_start_to_name[start_addr] = []
                func_start_to_name[start_addr].append(symbol.name)

        if self.debug_sym_file is not None:
            with open(self.debug_sym_file, "rb") as f:
                symtab = ELFFile(f).get_section_by_name(".symtab")
                set_symbols(symtab)
            return func_start_to_name
        else:
            if self._has_symtab():
                symtab = self._elffile.get_section_by_name(".symtab")
                set_symbols(symtab)
            dynsymtab = self._elffile.get_section_by_name(".dynsym")
            set_symbols(dynsymtab)
            return func_start_to_name

    def _set_func_names(self):
        func_start_to_name = self._get_symbols()
        for f in self._functions:
            start = f.start
            if start not in func_start_to_name:
                continue
            f.name = func_start_to_name[start][0]

    def _set_function_prototype(self):
        # angr is a heavy-edition (rich mode) dependency; import lazily.
        import angr

        logger.info("Analyzing function prototypes in %s", self.so_path)
        project = angr.Project(self.so_path, auto_load_libs=False)
        base_addr = project.loader.main_object.min_addr
        cfg = project.analyses.CFGFast(normalize=True)
        for _, func in cfg.kb.functions.items():
            func_addr = func.addr - base_addr
            if func_addr not in self._addr_to_function:
                continue
            # Try to determine number of arguments using calling convention analysis
            project.analyses.VariableRecoveryFast(func)
            cc = project.analyses.CallingConvention(func)
            target_func = self._addr_to_function.get(func_addr)
            if cc and cc.prototype:
                target_func.num_args = len(cc.prototype.args)
                target_func.args_size = []
                for arg in cc.prototype.args:
                    if isinstance(arg.size, int):
                        target_func.args_size.append(arg.size)
                    else:
                        target_func.args_size.append(0)  # unknown size
                if cc.prototype.returnty and isinstance(cc.prototype.returnty.size, int):
                    target_func.ret_size = cc.prototype.returnty.size

    def _create_functions(self):
        # add detected functions
        analyzed_addrs = set()
        text_start_addr = self._elffile.get_section_by_name(".text")["sh_addr"]
        text_end_addr = text_start_addr + self._elffile.get_section_by_name(".text")["sh_size"]
        entry_addrs = self._function_boundary_detection()
        # remove address outside .text section
        entry_addrs = [addr for addr in entry_addrs if text_start_addr <= addr <= text_end_addr]
        # add fini_array and init_array functions
        init_fini_pointers = self._read_init_fini_array()
        # filter out zero pointers
        init_fini_pointers = [addr for addr in init_fini_pointers if addr != 0]
        entry_addrs.extend(init_fini_pointers)
        entry_addrs = sorted(set(entry_addrs))  # remove duplicates and sort
        if not entry_addrs:
            raise ValueError(f"No function entry addresses detected in {self.so_path}")
        for i in range(1, len(entry_addrs)):
            start = entry_addrs[i - 1]
            end = entry_addrs[i]
            if start in analyzed_addrs:
                continue
            analyzed_addrs.add(start)
            self._functions.append(
                Function(start, end, f"boundary_detected_{hex(start)}", self.so_path)
            )

        self._functions.append(
            Function(
                entry_addrs[-1],
                text_end_addr,
                f"boundary_detected_{hex(entry_addrs[-1])}",
                self.so_path,
            )
        )

        # add init/fini functions
        init_section = self._elffile.get_section_by_name(".init")
        if init_section:
            init_start = init_section["sh_addr"]
            init_end = init_start + init_section["sh_size"]
            self._functions.append(Function(init_start, init_end, ".init", self.so_path))
        fini_section = self._elffile.get_section_by_name(".fini")
        if fini_section:
            fini_start = fini_section["sh_addr"]
            fini_end = fini_start + fini_section["sh_size"]
            self._functions.append(Function(fini_start, fini_end, ".fini", self.so_path))

        # sort by start address
        self._functions.sort(key=lambda f: f.start)
        for f in self._functions:
            self._addr_to_function[f.start] = f

    def decode(self):
        executable_sections = self._list_executable_sections()
        for section_name in executable_sections:
            section_data = self._elffile.get_section_by_name(section_name).data()
            section_base_address = self._elffile.get_section_by_name(section_name)["sh_addr"]
            instructions = disassemble_data(section_data, section_base_address)
            prev_insn = None
            for insn in instructions:
                instruction = Instruction(insn, section_name, so_path=self.so_path)
                instruction.prev = prev_insn
                self._instructions.append(instruction)
                self._addr_to_instruction[insn.address] = instruction
                if prev_insn is not None:
                    prev_insn.next = instruction
                prev_insn = instruction

    def dump(self, output_file=None):
        if output_file is None:
            output_file = os.path.basename(self.so_path) + ".disasm"
        with open(output_file, "w") as f:
            executable_sections = self._list_executable_sections()
            for section_name in executable_sections:
                f.write(f"Section: {section_name}\n")

            for insn in self._instructions:
                f.write(
                    f"{insn.address:#x} {insn.insn.mnemonic} "
                    f"{insn.insn.op_str} {insn.section_name}\n"
                )

    def get_instruction_at_address(self, address):
        if address in self._addr_to_instruction:
            return self._addr_to_instruction[address]
        else:
            logger.warning(
                "Address not found in cached instructions, disassembling on-the-fly: %#x.",
                address,
            )
            # find which section the address belongs to
            for section_name in self._list_executable_sections():
                section = self._elffile.get_section_by_name(section_name)
                section_base_address = section["sh_addr"]
                section_size = section["sh_size"]
                if section_base_address <= address < section_base_address + section_size:
                    section_data = section.data()
                    offset_in_section = address - section_base_address
                    if offset_in_section < len(section_data):
                        insn = disassemble_data(
                            section_data[offset_in_section : offset_in_section + 16],
                            section_base_address + offset_in_section,
                        )
                        if insn:
                            decoded_insn = Instruction(insn[0], section_name, so_path=self.so_path)
                            self._addr_to_instruction[address] = decoded_insn
                            self._instructions.append(decoded_insn)
                            return decoded_insn
            raise ValueError(f"Cannot find instruction at address {address:#x} in {self.so_path}")

    def _get_function_ind_at_address(self, address):
        # binary search for the function
        # not the exact address, but within the function range
        low, high = 0, len(self._functions) - 1
        while low <= high:
            mid = (low + high) // 2
            func = self._functions[mid]
            if func.start <= address < func.end:
                return mid
            elif address < func.start:
                high = mid - 1
            else:
                low = mid + 1
        return -1

    def get_function_at_address(self, address):
        # binary search for the function
        index = self._get_function_ind_at_address(address)
        if index == -1:
            return None
        return self._functions[index]

    def is_function_start(self, address):
        index = self._get_function_ind_at_address(address)
        if index == -1:
            return False
        return self._functions[index].start == address
