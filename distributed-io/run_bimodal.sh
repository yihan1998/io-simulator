#!/bin/bash

# Define the start, end, and stride values
load_start=0.05
load_end=1.20
load_stride=0.05

host=$(hostname -f)

function update_config() {
    echo " > Update config: preempt = ${preempt}, ws = ${ws}"
    jq '.preempt_enabled = '${preempt} configs/bimodal_config.json > configs/bimodal_config_1.json
    jq '.work_stealing_enabled = '${ws} configs/bimodal_config_1.json > configs/bimodal_config_2.json
}

function spawn_sim() {
    python3 simulation.py ../configs/bimodal_config_tmp.json bimodal_${preempt}_${ws}
    wait
}

function run_expriments() {
    preempt=$1
    ws=$2

    bimodal_dir=results/bimodal-${preempt}-${ws}

    mkdir ${bimodal_dir} 

    update_config

    for i in $(seq 0.05 0.05 1)
    do
        jq '.avg_system_load = '${i} configs/bimodal_config_2.json > configs/bimodal_config_tmp.json

        cd sim/

        spawn_sim

        cd ../

        mv results/sim_${host}_bimodal_${preempt}_${ws} ${bimodal_dir}/sim_bimodal_${preempt}_${ws}_${i}
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

rm configs/bimodal_*_tmp.json configs/bimodal_*_1.json configs/bimodal_*_2.json