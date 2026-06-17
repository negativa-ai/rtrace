#ifndef TYPES_H
#define TYPES_H
#include <string>
// Prefixed to avoid colliding with the TRAP_* enum that glibc's <signal.h>
// (pulled in via <sys/wait.h>) defines, e.g. TRAP_BRANCH.
const static uint8_t RTRACE_TRAP_START = 0;
const static uint8_t RTRACE_TRAP_BRANCH = 1;
const static uint8_t RTRACE_TRAP_RETURN = 2;

struct function_info_t
{
    uint16_t num_args;               // Number of arguments
    std::vector<uint64_t> arg_sizes; // Sizes of each argument
    uint64_t ret_size;               // Size of the return value
};

struct trap_info_t
{
    uint64_t start_address; // Start address of the function where the trap is located
    uint64_t trap_address;  // Address to be instrumented
    uint64_t trap_type;     // Type of trap (RTRACE_TRAP_START, RTRACE_TRAP_BRANCH, RTRACE_TRAP_RETURN)
};

#endif // TYPES_H