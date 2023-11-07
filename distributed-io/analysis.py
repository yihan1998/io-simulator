import numpy as np
import sys
import os
import json

RESULTS_DIR_NAME = "results/"
RESULTS_SUBDIR_NAME = RESULTS_DIR_NAME + "sim_{}/"
THREAD_RUN_FORMAT = "{}_t{}"
CPU_FILE_NAME = "cpu_usage.csv"
TASK_FILE_NAME = "task_times.csv"
META_FILE_NAME = "meta.json"
STATS_FILE_NAME = "stats.json"
CSV_HEADER = "Run ID,Cores,Sim Duration,Load,CPU Load,Task Load," \
             "Task Throughput,Throughput,RX Throughput,TX Throughput,Real Load,"    \
             "Total Median Latency,Total 95% Task Tail Latency,Total 99% Tail Latency,Total 99.9% Tail Latency, " \
             "In System Median Latency,In System 95% Task Tail Latency,In System 99% Tail Latency,In System 99.9% Tail Latency, " \
             "Rx HWQ Median Latency,Rx HWQ 95% Task Tail Latency,Rx HWQ 99% Tail Latency,Rx HWQ 99.9% Tail Latency,"    \
             "SWQ Median Latency,SWQ 95% Task Tail Latency,SWQ 99% Tail Latency,SWQ 99.9% Tail Latency,"    \
             "Tx HWQ Median Latency,Tx HWQ 95% Task Tail Latency,Tx HWQ 99% Tail Latency,Tx HWQ 99.9% Tail Latency"


def analyze_sim_run(name, run_name, output_file, print_results=False, time_dropped=0):
    # cpu_file = open(RESULTS_SUBDIR_NAME.format(run_name) + CPU_FILE_NAME, "r")
    # task_file = open(RESULTS_SUBDIR_NAME.format(run_name) + TASK_FILE_NAME, "r")
    # meta_file = open(RESULTS_SUBDIR_NAME.format(run_name) + META_FILE_NAME, "r")
    # stats_file = open(RESULTS_SUBDIR_NAME.format(run_name) + STATS_FILE_NAME, "r")
    cpu_file = open(run_name + '/' + CPU_FILE_NAME, "r")
    task_file = open(run_name + '/' + TASK_FILE_NAME, "r")
    meta_file = open(run_name + '/' + META_FILE_NAME, "r")
    stats_file = open(run_name + '/' + STATS_FILE_NAME, "r")

    meta_data = json.load(meta_file)
    stats = json.load(stats_file)

    meta_file.close()
    stats_file.close()

    # CPU Stats
    busy_time = 0
    task_time = 0
    network_time = 0
    switch_time = 0
    ws_time = 0
    successful_ws_time = 0
    unsuccessful_ws_time = 0

    next(cpu_file) # skip first line
    for line in cpu_file:
        data = line.strip().split(",")
        busy_time += int(data[1])
        task_time += int(data[2])
        network_time += int(data[3])
        switch_time += int(data[4])
        ws_time += int(data[5])
        successful_ws_time += int(data[6])
        unsuccessful_ws_time += int(data[7])

    cpu_file.close()

    cores = meta_data["num_cores"]
    avg_load = (busy_time / (cores * stats["End Time"]))
    avg_task_load = (task_time / (task_time + network_time + switch_time + ws_time))

    # Task Stats
    complete_tasks = stats["Completed Tasks"]
    rx_tasks = stats["Completed Rx"]
    tx_tasks = stats["Completed Tx"]
    total_tasks = 0

    task_total_latencies = []
    task_in_system_latencies = []
    task_rx_hwq_latencies = []
    task_swq_latencies = []
    task_tx_hwq_latencies = []

    tasks_stolen = 0
    total_steals = 0
    total_flag_steals = 0
    tasks_flag_stolen = 0
    total_flag_wait_time = 0
    total_flag_set_delay = 0
    total_queueing_time = 0
    total_requeue_wait_time = 0

    next(task_file) # skip first line
    for line in task_file:
        data = line.split(",")
        if int(data[0]) > time_dropped * stats["End Time"] and int(data[1]) >= 0:
            total_tasks += 1
            task_total_latencies.append(int(data[1]))
            task_in_system_latencies.append(int(data[2]))
            task_rx_hwq_latencies.append(int(data[3]))
            task_swq_latencies.append(int(data[4]))
            task_tx_hwq_latencies.append(int(data[5]))

    total_percentiles = np.percentile(task_total_latencies, [50, 95, 99, 99.9])
    in_system_percentiles = np.percentile(task_in_system_latencies, [50, 95, 99, 99.9])
    rx_hwq_percentiles = np.percentile(task_rx_hwq_latencies, [50, 95, 99, 99.9])
    swq_percentiles = np.percentile(task_swq_latencies, [50, 95, 99, 99.9])
    tx_hwq_percentiles = np.percentile(task_tx_hwq_latencies, [50, 95, 99, 99.9])

    task_file.close()

    throughput = (complete_tasks/stats["End Time"]) * 10**9
    task_throughput = (complete_tasks/stats["End Time"]) * 10**9
    rx_throughput = (rx_tasks/stats["End Time"]) * 10**9
    tx_throughput = (tx_tasks/stats["End Time"]) * 10**9
    real_load = (complete_tasks/stats["End Time"]) / ((cores/ meta_data["AVERAGE_SERVICE_TIME"]))

    avg_queueing_time = total_queueing_time / total_tasks if total_tasks > 0 else 0

    data_string = "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}".format(
        name, meta_data["num_cores"], meta_data["sim_duration"], 
        meta_data["avg_system_load"], avg_load * 100, avg_task_load * 100, 
        task_throughput, throughput, rx_throughput, tx_throughput, real_load * 100,
        total_percentiles[0], total_percentiles[1], total_percentiles[2], total_percentiles[3], 
        in_system_percentiles[0], in_system_percentiles[1], in_system_percentiles[2], in_system_percentiles[3], 
        rx_hwq_percentiles[0], rx_hwq_percentiles[1], rx_hwq_percentiles[2], rx_hwq_percentiles[3], 
        swq_percentiles[0], swq_percentiles[1], swq_percentiles[2], swq_percentiles[3], 
        tx_hwq_percentiles[0], tx_hwq_percentiles[1], tx_hwq_percentiles[2], tx_hwq_percentiles[3], 
         "\"{}\"".format(meta_data["description"]))
    output_file.write(data_string + "\n")


def main():
    # Arguments:
    # First arg is either a name of a file with a list of runs or the name of one run (or nothing to use entire results dir)
    # Second arg is output file
    # Third arg is how many of the first tasks to drop for task latency metrics

    if len(sys.argv) != 4:
        print("Invalid number of arguments.")
        exit(0)

    output_file_name = sys.argv[-2]
    output_file = open(output_file_name, "w")
    output_file.write(CSV_HEADER + "\n")

    sim_list = []
    name = sys.argv[1].strip()

    # File with list of sim names
    if os.path.isdir("./results/" + name):
        path = "./results/" + name + '/'
        sim_list = os.listdir(path)
        for sim_name in sim_list:
            analyze_sim_run(name, path + sim_name, output_file, time_dropped=int(sys.argv[-1])/100)
        print("Simulation analysis complete")

        # for folder in folders:
        #     output_result(name, path, folder)
        # sim_list_file = open(name)
        # sim_list = sim_list_file.readlines()
        # sim_list_file.close()

    # for sim_name in sim_list:
    #     analyze_sim_run(sim_name.strip(), output_file, time_dropped=int(sys.argv[-1])/100)
    #     print("Simulation {} analysis complete".format(sim_name))

    output_file.close()


if __name__ == "__main__":
    main()