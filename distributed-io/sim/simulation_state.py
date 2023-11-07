#!/usr/bin/env python
"""Object to maintain simulation state."""

import logging
import math
import datetime
import random
import numpy as np 

from timer import Timer
from tasks import Task
from sim_thread import WorkerThread, NetworkThread
from sim_queue import Queue
from sim_core import Core
import progress_bar as progress

class SimulationState:
    """Object to maintain simulation state as time passes."""

    def __init__(self, config):
        # Simulation Global Variables
        self.timer = Timer()
        self.worker_threads = []
        self.network_threads = []
        self.cores = []
        self.tasks = []
        self.hw_queues = []
        self.rx_queues = []
        self.tx_queues = []
        self.task_number = []

        # Global stats
        self.overall_steal_count = 0
        self.complete_task_count = 0
        self.complete_rx = 0
        self.complete_tx = 0
        self.work_steal_tasks = 0
        self.global_check_count = 0
        self.work_steal_tasks = 0

        # Stats only known at complete time
        self.tasks_scheduled = 0
        self.end_time = None
        self.sim_end_time = None

        # Optional stats
        self.config = config
        self.ws_checks = []

    def any_incomplete(self):
        """Return true if there are any incomplete tasks for the entire simulation."""
        return self.complete_task_count < self.tasks_scheduled

    def record_ws_check(self, local_id, remote, check_count, successful=False):
        """Record a work steal check on a queue to see if it can be stolen from."""
        if self.config.record_steals:
            if not successful:
                self.ws_checks.append((local_id, remote.id, self.timer.get_time() - remote.last_ws_check,
                                       remote.length(), check_count, False))
            else:
                self.ws_checks[-1] = (local_id, remote.id, self.timer.get_time() - remote.last_ws_check,
                                      remote.length(), check_count, True)


    def add_final_stats(self):
        """Add final global stats to to the simulation state."""
        self.end_time = self.timer.get_time()
        for tasks in self.tasks:
            self.tasks_scheduled += len(tasks)
        self.sim_end_time = datetime.datetime.now().strftime("%y-%m-%d_%H:%M:%S")
    
    def results(self):
        """Create a dictionary of important statistics for saving."""
        stats = {"Completed Tasks": self.complete_task_count,
                 "Completed Rx": self.complete_rx,
                 "Completed Tx": self.complete_tx,
                 "Tasks Scheduled": self.tasks_scheduled,
                 "Simulation End Time": self.sim_end_time, "End Time": self.end_time}
        return stats
    
    def total_queue_occupancy(self):
        """Return the total queue occupancy across all queues."""
        total = 0
        for q in self.queues:
            total += q.length()
        return total
    
    def bimodal(self, val1, prob1, val2, prob2):
        toss = random.choices((val1, val2), weights = [prob1, prob2])
        if toss[0] == val1:
            time = int(np.random.normal(val1, 0.01))
        else:
            time = int(np.random.normal(val2, 0.01))
        return time

    def initialize_state(self, config):
        """Initialize the simulation state based on the configuration."""
        if config.progress_bar:
            print("\nInitializing...")

        # Input validation
        if not config.validate():
            print("Invalid configuration")
            return

        random.seed(config.name)

        # Initialize hw queues
        for i in range(len(set(config.hw_queue_mapping))):
            self.hw_queues.append(Queue(i, config, self))
        self.available_hw_queues = list(set(config.hw_queue_mapping))

        # Initialize worker queues
        for i in range(len(set(config.worker_queue_mapping))):
            self.rx_queues.append(Queue(i, config, self))
            self.tx_queues.append(Queue(i, config, self))
        self.available_worker_queues = list(set(config.worker_queue_mapping))

        # Initialize threads
        for i in range(config.num_cores):
            hw_queue = self.hw_queues[config.hw_queue_mapping[i]]
            if self.config.num_worker_queues > 1:
                rx_queue = self.rx_queues[config.worker_queue_mapping[i]]
                tx_queue = self.tx_queues[config.worker_queue_mapping[i]]
            else:
                rx_queue = self.rx_queues[0]
                tx_queue = self.tx_queues[0]

            core = Core(i, rx_queue, tx_queue, config, self)

            network = NetworkThread(core, hw_queue, i, config, self)
            worker = WorkerThread(core, rx_queue, tx_queue, i, config, self)
            core.create_thread(network)
            core.create_thread(worker)

            self.cores.append(core)
            self.network_threads.append(network)
            self.worker_threads.append(worker)
            hw_queue.set_thread(i)
            rx_queue.set_thread(i)
            tx_queue.set_thread(i)

        # Set tasks and arrival times
        # Evenly distributed workload (TODO: imbalance)
        if config.bursty_arrivals:
            burst_count = config.BURST_SIZE
        else:
            burst_count = 1
        per_core_request_rate = config.avg_system_load / (config.ARRIVAL_RATE * burst_count)
        for thread in range(config.load_thread_count):
            tasks = []
            print("\nInitializing tasks for thread {}".format(thread))
            next_task_time = int(random.expovariate(per_core_request_rate))
            i = 0
            while (config.sim_duration is None or next_task_time < config.sim_duration) and \
                    (config.num_tasks is None or i < config.num_tasks):
                service_time = None 
                for j in range(burst_count):
                    while service_time is None or service_time == 0:
                        if config.constant_service_time:
                            service_time = config.AVERAGE_SERVICE_TIME
                        elif config.bimodal_service_time:
                            service_time = self.bimodal(config.BIMODAL_SERVICE_TIME_1, config.BIMODAL_PROB_1, config.BIMODAL_SERVICE_TIME_2, config.BIMODAL_PROB_2)
                        elif config.uniform_service_time:
                            service_time = int(random.uniform(0.5 * config.AVERAGE_SERVICE_TIME, 1.5 * config.AVERAGE_SERVICE_TIME))
                        elif config.normal_service_time:
                            service_time = int(np.random.normal(config.AVERAGE_SERVICE_TIME, 400.0))
                        elif config.lognormal_service_time:
                            service_time = int(np.random.lognormal(8.5, 0.25))
                        else:
                            service_time = int(random.expovariate(1 / config.AVERAGE_SERVICE_TIME))

                    tasks.append(Task(service_time, next_task_time, config, self))
                next_task_time += int(random.expovariate(per_core_request_rate))

                if config.progress_bar and i % 100 == 0:
                    progress.print_progress(next_task_time, config.sim_duration, decimals=3, length=50)
                i += 1

            self.tasks.append(tasks)