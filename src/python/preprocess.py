#!/home/ubuntu/miniconda3/envs/rtrace/bin/python
import argparse

from library import Library

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--so_path", help="Path to the shared object file")
    parser.add_argument(
        "--output", help="Path to output file of boundary detection")
    parser.add_argument("--method", help="Method to use for boundary detection of stripped binaries",
                        default="funseeker", choices=["ghidra", "nucleus", "linear", "funseeker", "angr"])
    parser.add_argument("--mode", type=int, default=0, choices=[0, 1],
                        help="0 for heavy mode, 1 for light mode")
    args = parser.parse_args()
    so_path = args.so_path
    output = args.output
    method = args.method
    mode = args.mode

    Library(so_path, analyze_function_prototypes=(
        mode == {mode}), func_info_dir=output)
