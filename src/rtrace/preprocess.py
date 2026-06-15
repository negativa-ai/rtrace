import argparse

from .edition import MODE_NAMES, MODE_RICH
from .library import Library

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--so_path", help="Path to the shared object file")
    parser.add_argument("--output", help="Path to output file of boundary detection")
    parser.add_argument(
        "--method",
        help="Method to use for boundary detection of stripped binaries",
        default="funseeker",
        choices=["ghidra", "nucleus", "linear", "funseeker", "angr"],
    )
    parser.add_argument(
        "--mode",
        choices=list(MODE_NAMES),
        default="rich",
        help="rich for full prototype analysis, light for lightweight tracing",
    )
    args = parser.parse_args()
    so_path = args.so_path
    output = args.output
    method = args.method
    mode = MODE_NAMES[args.mode]

    Library(so_path, analyze_function_prototypes=(mode == MODE_RICH), func_info_dir=output)
