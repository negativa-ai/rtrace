cmake_minimum_required(VERSION 3.16)
project(rtrace)
set(CMAKE_CXX_STANDARD 20)

set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)




add_library(rtrace SHARED rtrace.cc rtrace_util.h rtrace_util.cc types.h)
find_package(DynamoRIO)
if (NOT DynamoRIO_FOUND)
  message(FATAL_ERROR "DynamoRIO package required to build")
endif(NOT DynamoRIO_FOUND)
configure_DynamoRIO_client(rtrace)
use_DynamoRIO_extension(rtrace drmgr) 
use_DynamoRIO_extension(rtrace drreg) 
use_DynamoRIO_extension(rtrace drx) 
use_DynamoRIO_extension(rtrace drwrap) 
use_DynamoRIO_extension(rtrace drcontainers) 

include(FetchContent)
FetchContent_Declare(json URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz)
FetchContent_MakeAvailable(json)
target_link_libraries(rtrace nlohmann_json::nlohmann_json)
