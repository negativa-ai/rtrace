# RTrace

A high accurate library function call tracer.

## Usage

1. Start the dev container `./dev.sh`
2. Trace the workloads: 
```bash
LOG_DIR=/path/to/tracing/results
CMD=the_workload_cmd
MODE=1 # 0 for rich mode, 1 for light mode
python /home/ubuntu/repos/rtrace/src/python/main.py --logdir $LOG_DIR --mode $MODE -- $CMD
```
3. All detected function calls are recorded in files named `function-executed-xxx-xxxx.json` under `LOG_DIR`.

## Todo
1. Improve the documentation.
2. Package the tool so it can be installed more easily.

