def is_func_symbol(symbol_type_str):
    return symbol_type_str in ["STT_FUNC", "STT_GNU_IFUNC",  "STT_LOOS"]