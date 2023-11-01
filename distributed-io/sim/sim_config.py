#!/usr/bin/env python
"""Configuration of simulation parameters."""

import random


class SimConfig:
    """Object to hold all configuration state of the simulation. Remains constant."""

    def __init__(
        self,
        name=None,
        num_cores=None,
        num_threads=None,
        mapping=[],
        sim_duration=None,
        locking_enabled=True,
        ws_enabled=False,
        pb_enabled=True,
        constant_service_time=True,
        uniform_service_time=False,
        bimodal_service_time=False,
        trimodal_service_time=False,
        preempt_enabled=False,
    ):
        # Basic configuration
        self.name = name
        self.description = ""
        self.num_cores = num_cores
        self.num_threads = num_threads
        self.mapping = list(
            mapping
        )  # mapping is a list of queue numbers indexed by thread number
        self.sim_duration = sim_duration

        # Additional parameters
        self.locking_enabled = locking_enabled
        self.work_stealing_enabled = ws_enabled
        self.progress_bar = pb_enabled
        self.constant_service_time = constant_service_time
        self.bimodal_service_time = bimodal_service_time
        self.trimodal_service_time = trimodal_service_time
        self.uniform_service_time = uniform_service_time
        self.preempt_enabled = preempt_enabled

        self.TX_BATCH_SIZE = 64
        self.ARRIVAL_RATE = 1000
        self.AVERAGE_SERVICE_TIME = 1000
        self.LOCAL_QUEUE_CHECK_TIME = 0
        self.LOCAL_QUEUE_CHECK_TIMER = 1000
        self.PREEMPTION_TIME = 2000
        self.PREEMPTION_ITVL = 10000
        self.NETWORK_RX_TIME = 200
        self.NETWORK_TX_TIME = 200
        self.WORK_STEAL_CHECK_TIME = 120
        self.WORK_STEAL_TIME = 120

        # Record any additional file constants, ignoring recording ones
        self.constants = {}
        for key in globals().keys():
            if key.isupper() and "FORMAT" not in key and "FILE" not in key:
                self.constants[key] = globals()[key]

    def validate(self):
        """Validate configuration parameters."""
        # TODO: Update this for accuracy
        if self.num_cores == 0 or self.num_threads == 0:
            print("There must be nonzero queues and threads")
            return False

        if self.num_cores != len(set(self.mapping)):
            print("Number of queues does not match number in thread/queue mapping.")
            return False

        if self.work_stealing_enabled and self.num_queues == 1:
            print("Cannot work steal with one queue.")
            return False

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
