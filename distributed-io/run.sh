#!/bin/bash

# Define the start, end, and stride values
load_start=0.05
load_end=1.0
load_stride=0.05

host=$(hostname -f)

function update_config() {
    echo " > Update config: preempt = ${preempt}, ws = ${ws}"

    jq '.preempt_enabled = '${preempt} configs/bimodal_config.json > configs/bimodal_config_1.json
    jq '.preempt_enabled = '${preempt} configs/fix_config.json > configs/fix_config_1.json
    jq '.preempt_enabled = '${preempt} configs/uniform_config.json > configs/uniform_config_1.json

    jq '.work_stealing_enabled = '${ws} configs/bimodal_config_1.json > configs/bimodal_config_2.json
    jq '.work_stealing_enabled = '${ws} configs/fix_config_1.json > configs/fix_config_2.json
    jq '.work_stealing_enabled = '${ws} configs/uniform_config_1.json > configs/uniform_config_2.json
}

function spawn_sim() {
    python3 simulation.py ../configs/bimodal_config_tmp.json bimodal &
    python3 simulation.py ../configs/fix_config_tmp.json fix &
    python3 simulation.py ../configs/uniform_config_tmp.json uniform
    wait
}

function run_expriments() {
    preempt=$1
    ws=$2

    bimodal_dir=results/bimodal-${preempt}-${ws}
    fix_dir=results/fix-${preempt}-${ws}
    uniform_dir=results/uniform-${preempt}-${ws}

    mkdir ${bimodal_dir} ${fix_dir} ${uniform_dir}

    update_config

    for i in $(seq 0.05 0.05 1)
    do
        jq '.avg_system_load = '${i} configs/bimodal_config_2.json > configs/bimodal_config_tmp.json
        jq '.avg_system_load = '${i} configs/fix_config_2.json > configs/fix_config_tmp.json
        jq '.avg_system_load = '${i} configs/uniform_config_2.json > configs/uniform_config_tmp.json

        cd sim/

        spawn_sim

        cd ../

        mv results/sim_${host}_bimodal ${bimodal_dir}/sim_bimodal_${i}
        mv results/sim_${host}_fix ${fix_dir}/sim_fix_${i}
        mv results/sim_${host}_uniform ${uniform_dir}/sim_uniform_${i}
    done
}

# No preemption, No workstealing
run_expriments false false

# Preemption, No workstealing
run_expriments true false

# No preemption, Workstealing
run_expriments false true

# Preemption, Workstealing
run_expriments true true

rm configs/*_config_*_tmp.json configs/*_config_*_1.json configs/*_config_*_2.json