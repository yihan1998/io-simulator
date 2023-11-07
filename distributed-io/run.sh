#!/bin/bash

dist=$1
host=$(hostname -f)

function update_config() {
    preempt=$1
    ws=$2
    rate=$3
    echo " > Update config: preempt = ${preempt}, ws = ${ws}"
    jq '.preempt_enabled = '${preempt} configs/${dist}_config.json > configs/${dist}_${preempt}_${ws}_${rate}_config_1.json
    jq '.work_stealing_enabled = '${ws} configs/${dist}_${preempt}_${ws}_${rate}_config_1.json > configs/${dist}_${preempt}_${ws}_${rate}_config_2.json
    jq '.avg_system_load = '${rate} configs/${dist}_${preempt}_${ws}_${rate}_config_2.json > configs/${dist}_${preempt}_${ws}_${rate}_config_tmp.json

    rm configs/${dist}_${preempt}_${ws}_${rate}_*_1.json configs/${dist}_${preempt}_${ws}_${rate}_*_2.json
}

function spawn_sim() {
    preempt=$1
    ws=$2
    rate=$3
    python3 simulation.py ../configs/${dist}_${preempt}_${ws}_${rate}_config_tmp.json ${dist}_${preempt}_${ws}_${rate}
    wait
}
function run_expriment() {
    preempt=$1
    ws=$2
    rate=$3
    dir=$4

    update_config ${preempt} ${ws} ${rate}

    cd sim/

    spawn_sim ${preempt} ${ws} ${rate}

    cd ../

    mv results/sim_${host}_${dist}_${preempt}_${ws}_${rate} ${dir}/sim_${dist}_${preempt}_${ws}_${rate}
}

function run_expriments() {
    preempt=$1
    ws=$2

    dir=results/${dist}-${preempt}-${ws}

    mkdir ${dir} 

    for i in $(seq 0.05 0.05 1)
    do
        run_expriment ${preempt} ${ws} ${i} ${dir} &
    done

    wait
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

rm configs/${dist}_*_tmp.json