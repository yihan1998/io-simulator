#!/bin/bash

# Define the start, end, and stride values
load_start=0.05
load_end=1.0
load_stride=0.05

host=$(hostname -f)

function update_config() {
    echo " > Update config: preempt = ${preempt}, ws = ${ws}"
    jq '.preempt_enabled = '${preempt} configs/uniform_config.json > configs/uniform_config_1.json
    jq '.work_stealing_enabled = '${ws} configs/uniform_config_1.json > configs/uniform_config_2.json
}

function spawn_sim() {
    python3 simulation.py ../configs/uniform_config_tmp.json uniform_${preempt}_${ws}
    wait
}

function run_expriments() {
    preempt=$1
    ws=$2

    uniform_dir=results/uniform-${preempt}-${ws}

    mkdir ${uniform_dir} 

    update_config

    for i in $(seq 0.05 0.05 1)
    do
        jq '.avg_system_load = '${i} configs/uniform_config_2.json > configs/uniform_config_tmp.json

        cd sim/

        spawn_sim

        cd ../

        mv results/sim_${host}_uniform_${preempt}_${ws} ${uniform_dir}/sim_uniform_${preempt}_${ws}_${i}
    done
}

# No preemption, No workstealing
run_expriments false false &

# Preemption, No workstealing
run_expriments true false &

# No preemption, Workstealing
run_expriments false true &

# Preemption, Workstealing
run_expriments true true &

wait

rm configs/uniform_*_tmp.json configs/uniform_*_1.json configs/uniform_*_2.json