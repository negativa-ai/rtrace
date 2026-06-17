#include <algorithm>
#include <string>
#include <fstream>
#include <mutex>
#include <unordered_set>
#include <nlohmann/json.hpp>
#include <sstream>
#include <iomanip>

#include <iostream>
#include "rtrace_util.h"
#include "types.h"

const char *IGNORE_LIBRARIES[] = {"librtrace", "libdynamorio", "vdso", nullptr};

bool is_target_library(const char *lib_name)
{
    std::string lib_name_str{lib_name};
    for (const char *ignore_lib : IGNORE_LIBRARIES)
    {
        if (ignore_lib == nullptr)
            break;
        if (lib_name_str.find(ignore_lib) != std::string::npos)
        {
            return false;
        }
    }

    // check if the library name contains "so"
    if (lib_name_str.find("so") == std::string::npos)
    {
        return false;
    }

    return true;
}

bool str_contains(const char *str, const char *substr)
{
    if (str == nullptr || substr == nullptr)
        return false;
    return std::string(str).find(substr) != std::string::npos;
}

bool file_exists(const char *filename)
{
    if (filename == nullptr)
        return false;
    FILE *file = fopen(filename, "r");
    if (file)
    {
        fclose(file);
        return true;
    }
    return false;
}

std::vector<std::string> split_string(std::string s, std::string delimiter)
{
    size_t pos_start = 0, pos_end, delim_len = delimiter.length();
    std::string token;
    std::vector<std::string> res;

    while ((pos_end = s.find(delimiter, pos_start)) != std::string::npos)
    {
        token = s.substr(pos_start, pos_end - pos_start);
        pos_start = pos_end + delim_len;
        res.push_back(token);
    }

    res.push_back(s.substr(pos_start));
    return res;
}

bool read_function_info(const char *boundary_file, std::unordered_map<uint64_t, function_info_t> &start_addr_to_func_info_map, const uint64_t base_addr)
{
    std::ifstream file(boundary_file);
    if (!file.is_open())
    {
        std::cerr << "Failed to open file: " << boundary_file << std::endl;
        return false;
    }
    nlohmann::json function_info_data = nlohmann::json::parse(file);
    for (const auto &func : function_info_data)
    {
        uint64_t start_offset = func["start"];
        uint16_t num_args = std::max(static_cast<int>(func["num_args"]), 0);
        std::vector<uint64_t> arg_sizes;
        for (const auto &arg_size : func["args_size"])
        {
            arg_sizes.push_back(arg_size);
        }
        uint64_t ret_size = std::max(static_cast<int>(func["ret_size"]), 0);
        function_info_t func_info{
            num_args,
            arg_sizes,
            ret_size};
        uint64_t start_address = start_offset + base_addr;
        start_addr_to_func_info_map[start_address] = func_info;
    }
    file.close();
    return true;
}

void read_trap_info(const char *traps_file, std::unordered_map<uint64_t, trap_info_t> &trap_addr_to_trap_info_map, const uint64_t base_addr)
{
    std::ifstream file(traps_file);

    std::string line;
    std::getline(file, line); // Skip the first line (header)
    while (std::getline(file, line))
    {
        auto parts = split_string(line, "\t");
        if (parts.size() != 5)
        {
            std::cerr << "Invalid line in file: " << line << std::endl;
            exit(1);
        }

        uint64_t start_addr = std::stoul(parts[2], nullptr, 16) + base_addr;
        uint8_t trap_type = RTRACE_TRAP_START;
        if (parts[4] == "start")
        {
            trap_type = RTRACE_TRAP_START;
        }
        else if (parts[4] == "branch")
        {
            trap_type = RTRACE_TRAP_BRANCH;
        }
        else if (parts[4] == "return")
        {
            trap_type = RTRACE_TRAP_RETURN;
        }
        else
        {
            std::cerr << "Invalid trap type in file: " << line << std::endl;
            exit(1);
        }

        trap_info_t trap_info{
            start_addr,
            std::stoul(parts[3], nullptr, 16) + base_addr,
            trap_type};
        trap_addr_to_trap_info_map[trap_info.trap_address] = trap_info;
    }
    file.close();
}

void agg_trap_info(const std::unordered_map<uint64_t, trap_info_t> &trap_addr_to_trap_info_map, std::unordered_map<uint64_t, std::vector<uint64_t>> &start_addr_to_trap_addrs_map)
{
    for (const auto &pair : trap_addr_to_trap_info_map)
    {
        const trap_info_t &trap_info = pair.second;
        start_addr_to_trap_addrs_map[trap_info.start_address].push_back(trap_info.trap_address);
    }
}

static std::mutex file_mutex;
void write_file(std::ofstream &file, const std::string &content)
{
    file_mutex.lock();
    if (!file.is_open())
    {
        std::cerr << "File is not open!" << std::endl;
        return;
    }
    file << content << std::endl;
    file_mutex.unlock();
}

std::string byte_to_hex_string(uint8_t byte)
{
    std::ostringstream oss;
    oss << std::hex << std::setw(2) << std::setfill('0') << (int)byte;
    return oss.str();
}