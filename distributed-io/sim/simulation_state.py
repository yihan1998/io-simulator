#!/usr/bin/env python
"""Object to maintain simulation state."""

import math
import datetime
import random
import numpy as np 

from timer import Timer
from tasks import Task, NetworkRxTask
from sim_thread import Thread
from sim_queue import Queue
import progress_bar as progress

class SimulationState:
    """Object to maintain simulation state as time passes."""

    def __init__(self, config):
        # Simulation Global Variables
        self.timer = Timer()
        self.threads = []
        self.rx_pkts = []
        self.tx_pkts = []
        self.tasks = []
        self.queues = []

        # Global stats
        self.complete_rx_pkts = 0
        self.complete_tx_pkts = 0
        self.complete_task_count = 0

        # Preemption
        self.preemption_count = 0

        # Stats only known at complete time
        self.tasks_scheduled = 0
        self.end_time = None
        self.sim_end_time = None

        # Optional stats
        self.config = config

    def any_incomplete(self):
        """Return true if there are any incomplete tasks for the entire simulation."""
        return self.complete_task_count < self.rx_pkts_scheduled

    def add_final_stats(self):
        """Add final global stats to to the simulation state."""
        self.end_time = self.timer.get_time()
        self.tasks_scheduled = len(self.tasks)
        self.sim_end_time = datetime.datetime.now().strftime("%y-%m-%d_%H:%M:%S")
    
    def results(self):
        """Create a dictionary of important statistics for saving."""
        stats = {"Completed Tasks": self.complete_task_count,
                 "Completed RX": self.complete_rx_pkts,
                 "Completed TX": self.complete_tx_pkts,
                 "Tasks Scheduled": self.tasks_scheduled,
                 "Simulation End Time": self.sim_end_time, "End Time": self.end_time,
                 "Preemption count": self.preemption_count}
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
            time = int(np.random.normal(val1, 0.1))
        else:
            time = int(np.random.normal(val2, 0.1))
        return time
    
    def trimodal(self, val1, prob1, val2, prob2, val3, prob3):
        toss = random.choices((val1, val2, val3), weights = [prob1, prob2, prob3])
        if toss[0] == val1:
            time = int(np.random.normal(val1, 0.1))
        elif toss[0] == val2:
            time = int(np.random.normal(val2, 0.1))
        else:
            time = int(np.random.normal(val3, 0.1))
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

        # Initialize queues
        for i in range(len(set(config.mapping))):
            self.queues.append(Queue(i, config, self))
        self.available_queues = list(set(config.mapping))

        # Initialize threads
        for i in range(config.num_threads):
            queue = self.queues[config.mapping[i]]
            self.threads.append(Thread(queue, i, config, self))
            queue.set_thread(i)

        # Set tasks and arrival times
        # Evenly distributed workload (TODO: imbalance)
        request_rate = config.avg_system_load * config.load_thread_count / config.AVERAGE_SERVICE_TIME
        next_task_time = int(random.expovariate(request_rate))
        i = 0
        while (config.sim_duration is None or next_task_time < config.sim_duration) and \
                (config.num_tasks is None or i < config.num_tasks):
            service_time = None
            while service_time is None or service_time == 0:
                if config.constant_service_time:
                    service_time = config.AVERAGE_SERVICE_TIME
                elif config.bimodal_service_time:
                    service_time = self.bimodal(config.BIMODAL_SERVICE_TIME_1, config.BIMODAL_PROB_1, config.BIMODAL_SERVICE_TIME_2, config.BIMODAL_PROB_2)
                elif config.trimodal_service_time:
                    service_time = self.trimodal(config.TRIMODAL_SERVICE_TIME_1, config.TRIMODAL_PROB_1, config.TRIMODAL_SERVICE_TIME_2, config.TRIMODAL_PROB_2, config.TRIMODAL_SERVICE_TIME_3, config.TRIMODAL_PROB_3)
                elif config.uniform_service_time:
                    service_time = int(random.uniform(0.5 * config.AVERAGE_SERVICE_TIME, 1.5 * config.AVERAGE_SERVICE_TIME))
                else:
                    service_time = int(random.expovariate(1 / config.AVERAGE_SERVICE_TIME))

            # self.rx_pkts.append(Task(service_time, next_task_time, config, self))
            self.rx_pkts.append(NetworkRxTask(service_time, next_task_time, config, self))
            next_task_time += int(random.expovariate(request_rate))

            if config.progress_bar and i % 100 == 0:
                progress.print_progress(next_task_time, config.sim_duration, decimals=3, length=50)
            i += 1