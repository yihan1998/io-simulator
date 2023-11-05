#!/usr/bin/env python
"""Configuration of simulation parameters."""

import random
import logging

class SimConfig:
    """Object to hold all configuration state of the simulation. Remains constant."""

    def __init__(
        self,
        name=None,
        num_cores=None,
        num_hw_queues=None,
        num_worker_queues=None,
        hw_queue_mapping=[],
        worker_queue_mapping=[],
        sim_duration=None,
        locking_enabled=True,
        pb_enabled=True,
        bimodal_service_time=False,
        constant_service_time=True,
        uniform_service_time=False,
        preempt_enabled=False,
    ):
        # Basic configuration
        self.name = name
        self.description = ""
        self.num_cores = num_cores
        self.num_hw_queues = num_hw_queues
        self.num_worker_queues = num_worker_queues
        self.hw_queue_mapping = list(
            hw_queue_mapping
        )  # mapping is a list of queue numbers indexed by thread number
        self.worker_queue_mapping = list(
            worker_queue_mapping
        )  # mapping is a list of queue numbers indexed by thread number
        self.sim_duration = sim_duration

        # Additional parameters
        self.locking_enabled = locking_enabled
        self.progress_bar = pb_enabled
        self.bimodal_service_time = bimodal_service_time
        self.constant_service_time = constant_service_time
        self.uniform_service_time = uniform_service_time
        self.preempt_enabled = preempt_enabled

        self.ARRIVAL_RATE = 1000
        self.AVERAGE_SERVICE_TIME = 1000

        self.THREAD_SWITCH_TIME = 140

        self.NETWORK_POLL_TIME = 100
        self.NETWORK_RX_TIME = 200
        self.NETWORK_TX_TIME = 300

        self.LOCAL_QUEUE_CHECK_TIME = 0
        self.LOCAL_QUEUE_CHECK_TIMER = 1000

        self.PREEMPTION_TIME = 200
        self.PREEMPTION_ITVL = 5000

        # Record any additional file constants, ignoring recording ones
        self.constants = {}
        for key in globals().keys():
            if key.isupper() and "FORMAT" not in key and "FILE" not in key:
                self.constants[key] = globals()[key]

    def set_ws_permutation(self):
        """Shuffle queue list to decouple from allocation policy."""
        queues = list(range(self.num_worker_queues))
        random.shuffle(queues)
        self.WS_PERMUTATION = queues

    def validate(self):
        """Validate configuration parameters."""
        # TODO: Update this for accuracy
        if self.num_cores == 0 or self.num_hw_queues == 0 or self.num_worker_queues == 0:
            print("There must be nonzero queues and threads")
            return False

        if self.num_hw_queues != len(set(self.hw_queue_mapping)) or self.num_worker_queues != len(set(self.worker_queue_mapping)) :
            print("Number of queues does not match number in thread/queue mapping.")
            return False
        
        # Set the work steal permutation
        if self.num_worker_queues is not None:
            self.set_ws_permutation()
        else:
            self.WS_PERMUTATION = None

        # At least one way to decide when the simulation is over is needed
        if (
            (self.num_tasks is None and self.sim_duration is None)
            or (self.num_tasks is not None and self.num_tasks <= 0)
            or (self.sim_duration is not None and self.sim_duration <= 0)
        ):
            print(
                "There must be at least one way to decide when the simulation is over"
            )
            return False

        return True

    def __str__(self):
        return str(self.__dict__)

    @staticmethod
    def decode_object(o):
        a = SimConfig()
        a.__dict__.update(o)
        return a
