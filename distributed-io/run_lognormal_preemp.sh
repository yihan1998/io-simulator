#!/bin/bash

# Define the start, end, and stride values
load_start=0.05
load_end=1.0
load_stride=0.05

host=$(hostname -f)

function update_config() {
    preempt=$1
    preempt_rate=$2
    ws=$3
    rate=$4

    name=lognormal_${preempt}_${preempt_rate}_${ws}_${rate}_config

    echo " > Update config: preempt = ${preempt}, rate=${preempt_rate}, ws = ${ws}"
    jq '.preempt_enabled = '${preempt} configs/lognormal_config.json > configs/${name}_1.json
    jq '.PREEMPTION_ITVL = '${preempt_rate} configs/${name}_1.json > configs/${name}_2.json
    jq '.work_stealing_enabled = '${ws} configs/${name}_2.json > configs/${name}_3.json
    jq '.avg_system_load = '${rate} configs/${name}_3.json > configs/${name}_tmp.json

    rm configs/${name}_1.json configs/${name}_2.json configs/${name}_3.json
}

function spawn_sim() {
    preempt=$1
    preempt_rate=$2
    ws=$3
    rate=$4

    name=lognormal_${preempt}_${preempt_rate}_${ws}_${rate}

    python3 simulation.py ../configs/${name}_config_tmp.json ${name}

    wait
}

function run_expriment() {
    preempt=$1
    preempt_rate=$2
    ws=$3
    rate=$4
    lognormal_dir=$5

    name=lognormal_${preempt}_${preempt_rate}_${ws}_${rate}

    update_config ${preempt} ${preempt_rate} ${ws} ${rate}

    cd sim/

    spawn_sim ${preempt} ${preempt_rate} ${ws} ${rate}

    cd ../

    mv results/sim_${host}_${name} ${lognormal_dir}/sim_${name}
}

function run_expriments() {
    preempt=$1
    preempt_rate=$2
    ws=$3

    lognormal_dir=results/lognormal-${preempt}-${preempt_rate}-${ws}

    mkdir ${lognormal_dir} 

    for i in $(seq 0.05 0.05 1)
    do
        run_expriment ${preempt} ${preempt_rate} ${ws} ${i} ${lognormal_dir} &
    done

    wait
}

# No preemption, Workstealing
run_expriments false 0 true &

rates=("2000" "2500" "5000" "7000" "10000" "12000")
for preempt_rate in "${rates[@]}"
do
    run_expriments true ${preempt_rate} true &
done

wait