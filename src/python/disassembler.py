from capstone import *


DISASSEMBLER = Cs(CS_ARCH_X86, CS_MODE_64)
DISASSEMBLER.detail = True
DISASSEMBLER.skipdata = True


def disassemble_so_path(so_path):
    raise NotImplementedError("This function is not implemented yet.")


def disassemble_data(data, base):
    insns = []
    for insn in DISASSEMBLER.disasm(data, base):
        insns.append(insn)
    return insns

