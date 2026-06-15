
#include <cstdint>  /* for intptr */
#include <stddef.h> /* for offsetof */
#include <tuple>
#include <unordered_set>
#include <filesystem>
#include <iostream>
#include "dr_api.h"
#include "drmgr.h"
#include "drreg.h"
#include "drx.h"
#include "droption.h"
#include "drwrap.h"
#include "droption.h"

#include "rtrace_util.h"
#include "types.h"

#define DISPLAY_STRING(msg) dr_printf("%s\n", msg);

#define NULL_TERMINATE(buf) (buf)[(sizeof((buf)) / sizeof((buf)[0])) - 1] = '\0'

using ::dynamorio::droption::DROPTION_SCOPE_ALL;
using ::dynamorio::droption::DROPTION_SCOPE_CLIENT;
using ::dynamorio::droption::droption_t;

// trap_address: trap_info_t
static std::unordered_map<uint64_t, function_info_t> addr_to_func_info_map;

static const std::string INTERMEDIATE_DIR = "/home/ubuntu/repos/rtrace/experiments/cache/";

static std::unordered_set<std::string> analyzed_sos;
static std::unordered_set<uint64_t> instrumented_addrs; // fixme: multithread support
static void *stats_mutex;                               /* for multithread support */

static droption_t<int>
    MODE(DROPTION_SCOPE_CLIENT, "mode", 0, "Working mode",
         "0 for rich mode (full prototype analysis), 1 for light mode");

static droption_t<std::string>
    LOG_DIR(DROPTION_SCOPE_CLIENT, "log_dir", "./", "Output of tracing logs",
            "Output of tracing logs");

static droption_t<std::string>
    so_name(DROPTION_SCOPE_CLIENT, "so_name", "", "Target so name",
            "Empty string means all shared libraries will be traced");

static int tls_idx;
static std::string log_dir_str;

typedef struct
{
    file_t executed_instrumentations_f;
    file_t loaded_modules_f;
    file_t branch_taken_f;
    file_t func_args_ret_f;
    file_t block_info_f;
} log_file_t;

static std::string
gen_file_name(const std::string &pid, const std::string &tid, const std::string log_file_name)
{
    return log_dir_str + "/" + "rtrace-intermediate-" + pid + "-" + tid + "-" + log_file_name + ".log";
}

static bool
write_to_file(file_t file, std::string content)
{
    size_t content_size = content.size();
    const char *content_cstr = content.c_str();
    size_t written = 0;
    while ((written = dr_write_file(file, (const void *)content_cstr, content_size)) != content_size)
    {
        content += written;
        content_size -= written;
    }
    return written == content_size;
}

static void
wrap_pre(void *wrapcxt, DR_PARAM_OUT void **user_data)
{
    app_pc func_pc = drwrap_get_func(wrapcxt);
    void *drcontext = dr_get_current_drcontext();

    uint64_t func_pc_addr = (uint64_t)(uintptr_t)func_pc;
    function_info_t &func_info = addr_to_func_info_map[func_pc_addr];
    uint16_t num_args = func_info.num_args;
    std::string content = "Entry: " + std::to_string(func_pc_addr) + "\n";
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(drcontext, tls_idx);
    write_to_file(log_file->func_args_ret_f, content);
    for (uint16_t i = 0; i < num_args; ++i)
    {
        // todo: dynamorio only supports int https://github.com/dynamorio/dynamorio/issues/1104
        uint64_t arg = (uint64_t)drwrap_get_arg(wrapcxt, i);
        content = "Arg_" + std::to_string(i) + ": " + std::to_string(arg) + "\n";
        write_to_file(log_file->func_args_ret_f, content);
    }

    // This routine may de-reference application memory directly, so the caller should wrap in DR_TRY_EXCEPT if crashes must be avoided.
}

static void
wrap_post(void *wrapcxt, void *user_data)
{

    app_pc func_pc = drwrap_get_func(wrapcxt);
    void *drcontext = dr_get_current_drcontext();

    uint64_t func_pc_addr = (uint64_t)(uintptr_t)func_pc;
    function_info_t &func_info = addr_to_func_info_map[func_pc_addr];
    uint64_t ret_size = func_info.ret_size;
    std::string ret_val_hex_str = "";
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(drcontext, tls_idx);
    if (ret_size > 0)
    {
        uint64_t ret_val = (uint64_t)drwrap_get_retval(wrapcxt);
        std::string content = "Ret: " + std::to_string(ret_val) + "\n";
        write_to_file(log_file->func_args_ret_f, content);
    }
    std::string content = "Exit: " + std::to_string(func_pc_addr) + "\n";
    write_to_file(log_file->func_args_ret_f, content);
}

static void
event_module_load(void *drcontext, const module_data_t *info, bool loaded)
{
    if (!is_target_library(info->full_path))
    {
        dr_fprintf(STDERR, "Skipping module %s\n", info->full_path);
        return;
    }
    std::string target_so_name = so_name.get_value();
    if (target_so_name != "" && std::string(info->full_path).find(target_so_name) == std::string::npos)
    {
        return;
    }

    uint64_t start_addr = (uint64_t)(uintptr_t)info->start;
    uint64_t end_addr = (uint64_t)(uintptr_t)info->end;

    dr_mutex_lock(stats_mutex);
    if (analyzed_sos.find(info->full_path) != analyzed_sos.end())
    {
        dr_fprintf(STDERR, "Module %s already analyzed, skipping.\n", info->full_path);
        return;
    }
    const std::string boundary_detection_filename = INTERMEDIATE_DIR + "/" + std::string{info->names.file_name} + ".info";
    dr_fprintf(STDERR, "Analyzing module %s at base address %p\n",
               info->full_path, (void *)start_addr);
    if (!file_exists(boundary_detection_filename.c_str()))
    {
        system(("/home/ubuntu/repos/rtrace/src/python/preprocess.py --so_path " + std::string{info->full_path} + " --output " + INTERMEDIATE_DIR).c_str());
    }

    std::string content = std::string{info->full_path} + ":" + std::to_string(start_addr) + ":" + std::to_string(end_addr) + "\n";
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(drcontext, tls_idx);
    write_to_file(log_file->loaded_modules_f, content);

    bool success = read_function_info(boundary_detection_filename.c_str(), addr_to_func_info_map, start_addr);
    if (success)
    {
        for (const auto &pair : addr_to_func_info_map)
        {
            app_pc func_pc = (app_pc)(uintptr_t)pair.first;
            if (!drwrap_wrap(func_pc, wrap_pre, wrap_post))
            {
                dr_fprintf(STDERR, "Failed to wrap function at %p\n", func_pc);
            }
        }
    }

    dr_fprintf(STDERR, "Analyzed module %s\n", info->full_path);
    dr_mutex_unlock(stats_mutex);
}

static void
event_module_load_light(void *drcontext, const module_data_t *info, bool loaded)
{
    if (!is_target_library(info->full_path))
    {
        dr_fprintf(STDERR, "Skipping module %s\n", info->full_path);
        return;
    }

    uint64_t start_addr = (uint64_t)(uintptr_t)info->start;
    uint64_t end_addr = (uint64_t)(uintptr_t)info->end;

    std::string content = std::string{info->full_path} + ":" + std::to_string(start_addr) + ":" + std::to_string(end_addr) + "\n";
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(drcontext, tls_idx);
    write_to_file(log_file->loaded_modules_f, content);
}

static void
at_call(app_pc src, app_pc targ)
{
    uint64_t src_addr = (uint64_t)(uintptr_t)src;
    uint64_t targ_addr = (uint64_t)(uintptr_t)targ;

    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(dr_get_current_drcontext(), tls_idx);
    write_to_file(log_file->branch_taken_f, std::to_string(src_addr) + "\n");
    write_to_file(log_file->branch_taken_f, std::to_string(targ_addr) + "\n");
}

static void
at_cbr(app_pc src, app_pc targ, app_pc fall, int taken, void *bb_addr)
{
    uint64_t src_addr = (uint64_t)(uintptr_t)src;

    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(dr_get_current_drcontext(), tls_idx);
    write_to_file(log_file->branch_taken_f, std::to_string(src_addr) + "\n");
    if (taken)
    {
        uint64_t targ_addr = (uint64_t)(uintptr_t)targ;
        write_to_file(log_file->branch_taken_f, std::to_string(targ_addr) + "\n");
    }
    else
    {
        uint64_t fall_addr = (uint64_t)(uintptr_t)fall;
        write_to_file(log_file->branch_taken_f, std::to_string(fall_addr) + "\n");
    }
}

static void
at_mbr(app_pc src, app_pc targ)
{
    uint64_t src_addr = (uint64_t)(uintptr_t)src;
    uint64_t targ_addr = (uint64_t)(uintptr_t)targ;
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(dr_get_current_drcontext(), tls_idx);
    write_to_file(log_file->branch_taken_f, std::to_string(src_addr) + "\n");
    write_to_file(log_file->branch_taken_f, std::to_string(targ_addr) + "\n");
}

static void
at_ubr(app_pc src, app_pc targ)
{
    uint64_t src_addr = (uint64_t)(uintptr_t)src;
    uint64_t targ_addr = (uint64_t)(uintptr_t)targ;
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(dr_get_current_drcontext(), tls_idx);
    write_to_file(log_file->branch_taken_f, std::to_string(src_addr) + "\n");
    write_to_file(log_file->branch_taken_f, std::to_string(targ_addr) + "\n");
}

static void
log_executed_bb(uint64_t bb_first_addr)
{
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(dr_get_current_drcontext(), tls_idx);
    write_to_file(log_file->func_args_ret_f, "BB: " + std::to_string(bb_first_addr) + "\n");
}

static dr_emit_flags_t
event_bb_analysis(void *drcontext, void *tag, instrlist_t *bb, bool for_trace,
                  bool translating, DR_PARAM_OUT void **user_data)
{
    instr_t *instr, *next_instr;
    instr = instrlist_first(bb);
    app_pc addr = instr_get_app_pc(instr); // todo: remove this line and the following assert
    DR_ASSERT(addr == (app_pc)tag);
    size_t bb_size = (size_t)drx_instrlist_app_size(bb);
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(drcontext, tls_idx);
    write_to_file(log_file->block_info_f,
                  std::to_string((uint64_t)(uintptr_t)addr) + ": " + std::to_string(bb_size) + "\n");

    return DR_EMIT_DEFAULT;
}

static dr_emit_flags_t
event_app_instruction(void *drcontext, void *tag, instrlist_t *bb, instr_t *inst,
                      bool for_trace, bool translating, void *user_data)
{
    if (!instr_is_app(inst))
        return DR_EMIT_DEFAULT;

    app_pc pc = instr_get_app_pc(inst);
    uint64_t pc_addr = (uint64_t)(uintptr_t)pc;

    if (instrumented_addrs.find(pc_addr) == instrumented_addrs.end())
    {

        if (instr_is_mbr(inst))
        {
            dr_insert_mbr_instrumentation(drcontext, bb, inst, (void *)at_mbr, SPILL_SLOT_1);
            instrumented_addrs.insert(pc_addr);
        }
        else if (instr_is_call(inst))
        {
            dr_insert_call_instrumentation(drcontext, bb, inst, (void *)at_call);
            instrumented_addrs.insert(pc_addr);
        }
        else if (instr_is_cbr(inst))
        {
            dr_insert_cbr_instrumentation_ex(drcontext, bb, inst, (void *)at_cbr, OPND_CREATE_INTPTR(dr_fragment_app_pc(tag)));
            instrumented_addrs.insert(pc_addr);
        }
        else if (instr_is_ubr(inst))
        {
            dr_insert_ubr_instrumentation(drcontext, bb, inst, (void *)at_ubr);
            instrumented_addrs.insert(pc_addr);
        }
        else if (instr_is_return(inst))
        {
            dr_insert_mbr_instrumentation(drcontext, bb, inst, (void *)at_mbr, SPILL_SLOT_1);
            instrumented_addrs.insert(pc_addr);
        }
    }

    if (!instr_is_cti(inst))
    {
        return DR_EMIT_DEFAULT;
    }

    drmgr_disable_auto_predication(drcontext, bb);
    dr_insert_clean_call(drcontext, bb, inst, (void *)log_executed_bb,
                         false /* not a call */, 1 /* num args */, OPND_CREATE_INTPTR((intptr_t)tag));
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(drcontext, tls_idx);
    write_to_file(log_file->executed_instrumentations_f, std::to_string(pc_addr) + "\n");

    return DR_EMIT_DEFAULT;
}

static dr_emit_flags_t
event_app_instruction_lightweight(void *drcontext, void *tag, instrlist_t *bb, instr_t *inst,
                                  bool for_trace, bool translating, void *user_data)
{
    if (!instr_is_app(inst))
        return DR_EMIT_DEFAULT;

    app_pc pc = instr_get_app_pc(inst);
    uint64_t pc_addr = (uint64_t)(uintptr_t)pc;

    if (!instr_is_cti(inst))
    {
        return DR_EMIT_DEFAULT;
    }

    drmgr_disable_auto_predication(drcontext, bb);
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(drcontext, tls_idx);
    write_to_file(log_file->executed_instrumentations_f, std::to_string(pc_addr) + "\n");

    return DR_EMIT_DEFAULT;
}

static void
flush_and_close_log_files(void *drcontext)
{
    log_file_t *log_file = (log_file_t *)(ptr_uint_t)drmgr_get_tls_field(drcontext, tls_idx);
    DR_ASSERT(log_file != NULL);
    dr_flush_file(log_file->executed_instrumentations_f);
    dr_close_file(log_file->executed_instrumentations_f);

    dr_flush_file(log_file->loaded_modules_f);
    dr_close_file(log_file->loaded_modules_f);

    dr_flush_file(log_file->branch_taken_f);
    dr_close_file(log_file->branch_taken_f);

    dr_flush_file(log_file->func_args_ret_f);
    dr_close_file(log_file->func_args_ret_f);

    dr_flush_file(log_file->block_info_f);
    dr_close_file(log_file->block_info_f);
    dr_thread_free(drcontext, log_file, sizeof(log_file_t));
}

static void
event_exit(void)
{

    drmgr_unregister_tls_field(tls_idx);
    drmgr_unregister_bb_insertion_event(event_app_instruction);
    dr_mutex_destroy(stats_mutex);
    drx_exit();
    drwrap_exit();
    drreg_exit();
    drmgr_exit();
}

static void
event_thread_init(void *drcontext)
{
    std::string pid_str = std::to_string(dr_get_process_id_from_drcontext(drcontext));
    std::string tid_str = std::to_string(dr_get_thread_id(drcontext));

    file_t executed_instrumentations_f = dr_open_file(gen_file_name(pid_str, tid_str, "executed_instrumentations").c_str(), DR_FILE_WRITE_OVERWRITE);
    DR_ASSERT(executed_instrumentations_f != INVALID_FILE);

    std::string filename = gen_file_name(pid_str, tid_str, "loaded_modules");
    file_t loaded_modules_f = dr_open_file(filename.c_str(), DR_FILE_WRITE_OVERWRITE);
    DR_ASSERT(loaded_modules_f != INVALID_FILE);

    file_t branch_taken_f = dr_open_file(gen_file_name(pid_str, tid_str, "branch_taken").c_str(), DR_FILE_WRITE_OVERWRITE);
    DR_ASSERT(branch_taken_f != INVALID_FILE);

    file_t func_args_ret_f = dr_open_file(gen_file_name(pid_str, tid_str, "func_args_ret").c_str(), DR_FILE_WRITE_OVERWRITE);
    DR_ASSERT(func_args_ret_f != INVALID_FILE);

    file_t block_info_f = dr_open_file(gen_file_name(pid_str, tid_str, "block_info").c_str(), DR_FILE_WRITE_OVERWRITE);
    DR_ASSERT(block_info_f != INVALID_FILE);

    log_file_t *log_file = (log_file_t *)dr_thread_alloc(drcontext, sizeof(log_file_t));
    DR_ASSERT(drmgr_set_tls_field(drcontext, tls_idx, (void *)(ptr_uint_t)log_file));
    log_file->executed_instrumentations_f = executed_instrumentations_f;
    log_file->loaded_modules_f = loaded_modules_f;
    log_file->branch_taken_f = branch_taken_f;
    log_file->func_args_ret_f = func_args_ret_f;
    log_file->block_info_f = block_info_f;
}

static void
event_thread_exit(void *drcontext)
{
    flush_and_close_log_files(drcontext);
}

DR_EXPORT void
dr_client_main(client_id_t id, int argc, const char *argv[])
{
    /* Parse command-line options. */
    if (!dynamorio::droption::droption_parser_t::parse_argv(
            dynamorio::droption::DROPTION_SCOPE_CLIENT, argc, argv, NULL, NULL))
        DR_ASSERT(false);

    dr_set_client_name("RTrace", "For better visibility of shared library execution");
    int mode = MODE.get_value();
    if (!drmgr_init() || !drx_init() || !drwrap_init())
        DR_ASSERT(false);

    stats_mutex = dr_mutex_create();
    log_dir_str = LOG_DIR.get_value();
    dr_fprintf(STDERR, "mode: %d\n", mode);
    std::filesystem::path log_dir_path(log_dir_str);
    if (log_dir_path.is_relative())
    {
        dr_fprintf(STDERR, "Log directory path is must be absolute, got: %s\n", log_dir_str.c_str());
        exit(1);
    }
    if (!std::filesystem::exists(log_dir_path))
    {
        std::filesystem::create_directories(log_dir_path);
    }

    /* Register opcode event. */
    dr_register_exit_event(event_exit);
    DR_ASSERT(drmgr_register_thread_init_event(event_thread_init));
    DR_ASSERT(drmgr_register_thread_exit_event(event_thread_exit));
    if (mode == 0)
    {
        DR_ASSERT(drmgr_register_bb_instrumentation_event(event_bb_analysis, event_app_instruction, NULL));
        DR_ASSERT(drmgr_register_module_load_event(event_module_load));
    }
    else
    {
        DR_ASSERT(drmgr_register_bb_instrumentation_event(NULL, event_app_instruction_lightweight, NULL));
        DR_ASSERT(drmgr_register_module_load_event(event_module_load_light));
    }

    tls_idx = drmgr_register_tls_field();
    DR_ASSERT(tls_idx > -1);
    /* Make it easy to tell, by looking at log file, which client executed. */
    dr_fprintf(STDERR, "Rtrace started\n");
}