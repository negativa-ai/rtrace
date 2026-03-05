#ifndef RTRACE_UTIL_H
#define RTRACE_UTIL_H
#include <string>
#include <unordered_map>
#include <vector>
#include <fstream>
#include "types.h"

bool is_target_library(const char *lib_name);
bool str_contains(const char *str, const char *substr);
bool file_exists(const char *filename);
bool read_function_info(const char *boundary_file, std::unordered_map<uint64_t, function_info_t> &start_addr_to_func_info_map, const uint64_t base_addr);
void read_trap_info(const char *traps_file, std::unordered_map<uint64_t, trap_info_t> &trap_addr_to_trap_info_map, const uint64_t base_addr);
void agg_trap_info(const std::unordered_map<uint64_t, trap_info_t> &trap_addr_to_trap_info_map, std::unordered_map<uint64_t, std::vector<uint64_t>> &start_addr_to_trap_addrs_map);
std::vector<std::string> split_string(std::string s, std::string delimiter);
void write_file(std::ofstream &file, const std::string &content);
std::string byte_to_hex_string(uint8_t byte);
#endif // RTRACE_UTIL_H