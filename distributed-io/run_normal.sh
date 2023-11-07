#!/bin/bash

# Define the start, end, and stride values
load_start=0.05
load_end=1.0
load_stride=0.05

host=$(hostname -f)

function update_config() {
    preempt=$1
    ws=$2
    rate=$3
    echo " > Update config: preempt = ${preempt}, ws = ${ws}"
    jq '.preempt_enabled = '${preempt} configs/normal_config.json > configs/normal_${preempt}_${ws}_${rate}_config_1.json
    jq '.work_stealing_enabled = '${ws} configs/normal_${preempt}_${ws}_${rate}_config_1.json > configs/normal_${preempt}_${ws}_${rate}_config_2.json
    jq '.avg_system_load = '${rate} configs/normal_${preempt}_${ws}_${rate}_config_2.json > configs/normal_${preempt}_${ws}_${rate}_config_tmp.json

    rm configs/normal_${preempt}_${ws}_${rate}_*_1.json configs/normal_${preempt}_${ws}_${rate}_*_2.json
}

function spawn_sim() {
    preempt=$1
    ws=$2
    rate=$3
    python3 simulation.py ../configs/normal_${preempt}_${ws}_${rate}_config_tmp.json normal_${preempt}_${ws}_${rate}
    wait
}
function run_expriment() {
    preempt=$1
    ws=$2
    rate=$3
    normal_dir=$4

    update_config ${preempt} ${ws} ${rate}

    cd sim/

    spawn_sim ${preempt} ${ws} ${rate}

    cd ../

    mv results/sim_${host}_normal_${preempt}_${ws}_${rate} ${normal_dir}/sim_normal_${preempt}_${ws}_${rate}
}

function run_expriments() {
    preempt=$1
    ws=$2

    normal_dir=results/normal-${preempt}-${ws}

    mkdir ${normal_dir} 

    for i in $(seq 0.05 0.05 1)
    do
        run_expriment ${preempt} ${ws} ${i} ${normal_dir} &
    done

    wait
}

# # No preemption, No workstealing
# run_expriments false false &

# # Preemption, No workstealing
# run_expriments true false &

# No preemption, Workstealing
run_expriments false true &

# Preemption, Workstealing
run_expriments true true &

wait

rm configs/normal_*_tmp.json configs/normal_*_1.json configs/normal_*_2.json