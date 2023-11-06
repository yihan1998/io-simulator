#!/usr/bin/env python
"""All tasks which can occupy a core's time."""

import math
import random
import logging

class Task:
    """Task to be completed by a thread."""

    def __init__(self, time, arrival_time, config, state):
        self.source_core = None
        self.service_time = time
        self.preempt_count = 0
        self.time_left = time
        self.complete = False
        self.arrival_time = arrival_time
        self.start_time = None
        self.completion_time = 0
        self.total_queue = None
        self.queue_checks = 0
        self.last_sched = None
        self.is_idle = False
        self.is_productive = True
        self.is_overhead = False
        self.steal_count = 0

        self.original_queue = None
        self.requeue_time = None

        self.preempted = False

        self.enter_sw_queue = 0
        self.leave_sw_queue = 0
        self.leave_hw_queue = 0

        self.preemption_timer = config.PREEMPTION_ITVL

        self.service_time = time

        self.config = config
        self.state = state

    def time_in_system(self):
        """Returns time that the task has been in the system (arrival to completion)."""
        return self.completion_time - self.arrival_time + 1

    def requeue_wait_time(self):
        """Returns time that the task spent not in its final queue."""
        if self.requeue_time is None:
            return 0
        return self.requeue_time - self.arrival_time + 1
    
    def process(self, time_increment=1, stop_condition=None, preempted=False):
        """Process the task for given time step.
        :param time_increment: Time step.
        :param stop_condition: Additional condition that must be met for the task to complete other than no more time
        left.
        """
        logging.debug("Current task {} service time: {}, left: {}".format(self.__class__, self.service_time, self.time_left))
        if self.time_left == self.service_time:
            self.start_time = self.state.timer.get_time()
            self.last_sched = self.state.timer.get_time()

        self.time_left -= time_increment

        # Any processing that must be done with the decremented timer but before the time left is checked
        self.process_logic()

        # If preemption enabled, check if the task has been preempted
        if (
            self.config.preempt_enabled
            and preempted is True
            and self.time_left > 0
        ):
            logging.debug("Task {} got preempted".format(self))
            self.preempt_count += 1
            self.preempted = True

        # If no more time left and stop condition is met, complete the task
        if self.time_left <= 0 and (stop_condition is None or stop_condition()):
            self.complete = True
            self.completion_time = self.state.timer.get_time()
            self.on_complete()

    def process_logic(self):
        """Any processing that must be done with the decremented timer but before the time left is checked."""
        pass

    def on_complete(self):
        """Complete the task and do any necessary accounting."""
        # Want to track how many vanilla tasks get completed
        self.state.complete_task_count += 1
        logging.debug("Task: {} is completed".format(self))

    def is_zero_duration(self):
        """True if the task has zero service time."""
        return self.service_time == 0

    def descriptor(self):
        return "Task (arrival {}, service time {}, original queue: {})".format(
            self.arrival_time, self.service_time, self.original_queue
        )

    def get_stats(self):
        stats = [
            self.arrival_time,
            self.leave_hw_queue - self.arrival_time + 1,
            self.time_in_system(),
            self.enter_sw_queue - self.arrival_time + 1,
            self.leave_sw_queue - self.enter_sw_queue + 1 - self.service_time,
            self.leave_hw_queue - self.leave_sw_queue + 1,
            self.service_time,
            self.preempt_count,
            self.steal_count,
            self.original_queue,
            self.total_queue,
            self.queue_checks,
            self.requeue_wait_time(),
        ]
        stats = [str(x) for x in stats]
        return stats

    @staticmethod
    def get_stat_headers(config):
        headers = [
            "Arrival Time",
            "Total Time",
            "Time in System",
            "Rx HWQ Time",
            "SWQ Time",
            "Tx HWQ Time",
            "Request Service Time",
            "Preempt Count", 
            "Steal Count",
            "Original Queue",
            "Total Queue Length",
            "Queue Checks",
            "Requeue Wait Time",
        ]
        return headers

    def __str__(self):
        if not self.complete:
            return self.descriptor() + ": time left of {}".format(self.time_left)
        else:
            return self.descriptor() + ": done at {}".format(self.completion_time)

    def __repr__(self):
        return str(self)

class NetworkPollTask(Task):
    """Task to run network stack to poll"""
    def __init__(self, thread, config, state):
        super().__init__(config.NETWORK_POLL_TIME, state.timer.get_time(), config, state)
        self.thread = thread
        self.is_productive = True
        self.is_overhead = False
    
    def on_complete(self):
        # Add TX task if finish queue is not empty
        if self.state.tx_queue.work_available() is True:
            logging.debug("Remain {} tasks in TX queue".format(self.state.tx_queue.work_remained()))
            batch = self.state.tx_queue.work_remained()
            tx_task = NetworkTxTask(self.thread, batch, self.config, self.state)
            self.thread.queue.enqueue(tx_task)

        # Poll HW queue 
        # 1. Infinite burst size
        num_recv = 0
        while self.state.task_number < len(self.state.tasks) and \
                self.state.tasks[self.state.task_number].arrival_time <= self.state.timer.get_time():
            task = self.state.tasks[self.state.task_number]
            # Enqueue tasks into network queue to be received
            rx_task = NetworkRxTask(self.thread, task, self.config, self.state)
            self.thread.queue.enqueue(rx_task)
            logging.debug("[HW RX]: {} onto network receive queue".format(task))
            self.state.task_number += 1
            num_recv += 1

        if num_recv > 0:
            logging.debug("Receive {} tasks".format(num_recv))

class NetworkRxTask(Task):
    def __init__(self, thread, task, config, state):
        super().__init__(config.NETWORK_RX_TIME, state.timer.get_time(), config, state)
        self.thread = thread
        self.is_productive = True
        self.is_overhead = False
        self.task = task

    def on_complete(self):
        # Add to worker queue
        self.state.rx_queue.enqueue(self.task)
        # Leave Hardware Queue and enter Software Queue
        self.task.enter_sw_queue = self.state.timer.get_time()
        self.state.complete_rx += 1
        logging.debug("Task: {} is received... rx: {}, tx: {}".format(self.task, self.state.complete_rx, self.state.complete_tx))

class NetworkTxTask(Task):
    def __init__(self, thread, batch, config, state):
        if batch == 1:
            duration = 60
        else:
            duration = math.floor(5.2 * batch + 80)

        logging.debug("Tx batch size: {}, run time: {}".format(batch, duration))

        super().__init__(duration, state.timer.get_time(), config, state)
        self.thread = thread
        self.batch = batch
        self.is_productive = True
        self.is_overhead = False

    def on_complete(self):
        # 1. Infinite burst size
        # Transmit in batch
        while self.state.tx_queue.work_available() is True:
            logging.debug("Remain {} tasks".format(self.state.tx_queue.work_remained()))
            task = self.state.tx_queue.dequeue()
            logging.debug("Task: {} is being transmitted... rx: {}, tx: {}".format(task, self.state.complete_rx, self.state.complete_tx))
            # Leave Hardware Queue and enter Software Queue
            task.leave_hw_queue = self.state.timer.get_time()
            self.state.complete_tx += 1

class PreemptionTask(Task):
    """Preemption task"""
    def __init__(self, thread, config, state):
        super().__init__(config.PREEMPTION_TIME, state.timer.get_time(), config, state)
        self.thread = thread
        self.is_productive = False
        self.is_overhead = True
        
    def on_complete(self):
        self.thread.core.preemption += 1

class LocalQueueCheckTask(Task):
    """Task to check the local queue of a thread."""

    def __init__(self, thread, config, state, return_to_ws_task=None):
        super().__init__(
            config.LOCAL_QUEUE_CHECK_TIME, state.timer.get_time(), config, state
        )
        self.thread = thread
        self.locked_out = not self.thread.queue.try_get_lock(self.thread.id)
        self.is_productive = False
        self.return_to_work_steal = return_to_ws_task is not None
        self.ws_task = return_to_ws_task
        self.start_work_search_spin = False

        # If no work stealing and there's nothing to get, start spin
        if (
            not config.work_stealing_enabled
            and config.LOCAL_QUEUE_CHECK_TIME == 0
            and not (self.thread.queue.work_available() or self.locked_out)
        ):
            self.service_time = 1
            self.time_left = 1
            self.is_idle = True

    def on_complete(self):
        """Grab new task from queue if available."""
        if self.locked_out:
            return

        # If work is available, take it
        elif self.thread.queue.work_available():
            self.thread.current_task = self.thread.queue.dequeue()
            self.thread.current_task.last_sched = self.state.timer.get_time()
            logging.debug("[DEQUEUE]: {} from queue".format(self.thread.current_task))
            self.thread.queue.unlock(self.thread.id)

    def descriptor(self):
        return "Local Queue Task (arrival {}, thread {})".format(
            self.arrival_time, self.thread.id
        )


class GlobalQueueCheckTask(Task):
    """Task to check the local queue of a thread."""

    def __init__(self, thread, config, state, return_to_ws_task=None):
        super().__init__(
            config.GLOBAL_QUEUE_CHECK_TIME, state.timer.get_time(), config, state
        )
        self.thread = thread
        self.locked_out = not self.thread.queue.try_get_lock(self.thread.id)
        self.is_productive = False
        self.return_to_work_steal = return_to_ws_task is not None
        self.ws_task = return_to_ws_task
        self.start_work_search_spin = False

        # If no work stealing and there's nothing to get, start spin
        if (
            not config.work_stealing_enabled
            and config.GLOBAL_QUEUE_CHECK_TIME == 0
            and not (self.thread.queue.work_available() or self.locked_out)
        ):
            self.service_time = 1
            self.time_left = 1
            self.is_idle = True

    def on_complete(self):
        """Grab new task from queue if available."""
        if self.locked_out:
            return

        # If work is available, take it
        elif self.thread.queue.work_available():
            self.thread.current_task = self.thread.queue.dequeue()
            self.thread.current_task.last_sched = self.state.timer.get_time()
            logging.debug("[DEQUEUE]: {} from queue".format(self.thread.current_task))
            self.thread.queue.unlock(self.thread.id)

    def descriptor(self):
        return "Local Queue Task (arrival {}, thread {})".format(
            self.arrival_time, self.thread.id
        )
