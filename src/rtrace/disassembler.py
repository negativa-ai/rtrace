"""Capstone-backed disassembly.

``capstone`` is a heavy-edition (mode 0) dependency, so it is imported lazily: the
disassembler is constructed on first use rather than at import time. This lets the
light edition import this module without ``capstone`` installed.
"""

_DISASSEMBLER = None


def _get_disassembler():
    global _DISASSEMBLER
    if _DISASSEMBLER is None:
        from capstone import CS_ARCH_X86, CS_MODE_64, Cs

        disassembler = Cs(CS_ARCH_X86, CS_MODE_64)
        disassembler.detail = True
        disassembler.skipdata = True
        _DISASSEMBLER = disassembler
    return _DISASSEMBLER


def disassemble_data(data, base):
    insns = []
    for insn in _get_disassembler().disasm(data, base):
        insns.append(insn)
    return insns
