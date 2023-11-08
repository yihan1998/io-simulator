#!/usr/bin/env python
"""All tasks which can occupy a core's time."""

from work_search_state import WorkSearchState
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

class AbstractWorkStealTask(Task):
    """Class to implement common functionality between different forms of work stealing tasks."""

    def __init__(self, thread, initial_time, config, state):
        super().__init__(initial_time, state.timer.get_time(), config, state)
        self.thread = thread
        self.work_found = False
        self.checked_all = False
        self.is_productive = False
        self.is_overhead = True
        self.check_count = 0

    def is_done(self):
        """Check if the task has found work or exhausted all options."""
        return self.work_found or self.checked_all

    def add_time(self, amount):
        """Add service time to the task."""
        if self.service_time is None:
            self.service_time = amount
            self.time_left = amount
        # When there is no overhead, may end up with -1 as time left
        elif self.time_left < 0:
            self.service_time += amount
            self.time_left = amount
        else:
            self.service_time += amount
            self.time_left += amount

    def check_can_work_steal(self, remote, get_lock_if_available=True):
        """Check that the task can steal from the remote queue.
        :param remote: Remote queue to steal from.
        :param get_lock_if_available: If true, actually get lock so that steal can occur.
        :returns: True if local thread can steal, otherwise false.
        """
        self.check_count += 1
        self.state.global_check_count += 1

        self.state.record_ws_check(self.thread.id, remote, self.check_count)
        remote.update_check_counts()
        remote.last_ws_check = self.state.timer.get_time()

        # If remote is the thread's own queue
        if remote.id == self.thread.queue.id:
            return False

        # If the thread cannot acquire its own lock (should already have it in most use cases)
        if not self.thread.queue.try_get_lock(self.thread.id):
            return False

        # If there is no work to steal
        if not remote.work_available():
            # logging.debug("Thread {} has nothing to steal from queue {}".format(self.thread.id, remote.id))
            return False

        # If the remote lock cannot be acquired
        if not remote.try_get_lock(self.thread.id, get_lock=get_lock_if_available):
            return False

        # Can work steal, record a successful check
        self.state.record_ws_check(
            self.thread.id, remote, self.check_count, successful=True
        )

        logging.debug("Thread {} work stealing from queue {}".format(self.thread.id, remote.id))
        return True

    def work_steal(self):
        """Steal work from remote queue.
        Takes the first half of tasks from the remote queue and adds to the front of local queue.
        """
        self.state.overall_steal_count += 1

        queue_length = self.remote.length()

        if queue_length > 0:
            self.thread.core.rx_queue.enqueue(self.remote.dequeue(), stolen=True)
        # stolen_tasks = []
        # # Avoid inverting the order of stolen tasks (stolen enqueues go to front of queue)
        # for i in range(math.ceil(queue_length / 2)):
        #     stolen_tasks.insert(0, self.remote.dequeue())
        # for task in stolen_tasks:
        #     self.thread.queue.enqueue(task, stolen=True)

        self.remote.unlock(self.thread.id)

class WorkStealTask(AbstractWorkStealTask):
    """Task to attempt to steal work from other queues."""

    def __init__(self, thread, config, state):
        super().__init__(thread, None, config, state)
        self.state.work_steal_tasks += 1
        self.original_search_index = (
            self.choose_first_queue()
            if self.config.two_choices
            else int(random.uniform(0, self.config.num_worker_queues))
        )
        self.search_index = self.original_search_index
        self.local_check_timer = (
            self.config.LOCAL_QUEUE_CHECK_TIMER if self.config.ws_self_checks else None
        )
        self.to_search = list(self.config.WS_PERMUTATION)
        self.candidate_remote = None

        # To initialize times and candidate remote, check first thread
        self.first_search()

    def choose_first_queue(self, num_choices=2):
        """Choose the first queue to search. Returns queue with oldest task of choices."""
        if num_choices >= self.config.num_worker_queues:
            choices = list(range(0, self.config.num_worker_queues))
        else:
            choices = []
            for i in range(num_choices):
                choices.append(int(random.uniform(0, self.config.num_worker_queues)))

        oldest_task_times = []
        for choice in choices:
            oldest_task = self.state.queues[choice].head()
            if oldest_task:
                oldest_task_times.append(oldest_task.arrival_time)
            else:
                oldest_task_times.append(self.state.timer.get_time())
        return choices[oldest_task_times.index(min(oldest_task_times))]

    def expected_completion_time(self):
        """Return current expected time that the task will complete."""
        if self.is_done():
            return self.state.timer.get_time() + self.time_left
        elif self.config.ws_self_checks:
            return min(
                self.state.timer.get_time() + self.time_left,
                self.state.timer.get_time() + self.local_check_timer,
            )
        else:
            return self.state.timer.get_time() + self.time_left

    def first_search(self):
        """Start the task by checking the sibling thread for work."""
        if self.config.random_work_steal_search:
            self.work_search_walk_random()
        elif (
            self.config.ws_sibling_first
            and self.thread.queue.id != self.thread.sibling.queue.id
        ):
            self.check_sibling()
        else:
            self.work_search_walk()

    def process(self, time_increment=1, stop_condition=None, preempted=False):
        """Process task and update work steal accounting."""
        if not self.is_zero_duration():
            self.thread.work_stealing_time += time_increment
            if any(q.work_available() for q in self.state.rx_queues):
                self.thread.non_work_conserving_time += time_increment
            if self.config.ws_self_checks:
                self.local_check_timer -= time_increment
        super().process(time_increment=time_increment, stop_condition=self.is_done)

    def process_logic(self):
        """Search other queues for work to steal."""
        if not self.work_found and self.time_left <= 0:  # Forces sequential checks
            # Check current candidate
            if self.check_can_work_steal(self.candidate_remote):
                self.work_found = True
                self.remote = self.candidate_remote
                self.start_work_steal()

            # If no flag to check, continue search for work until all have been checked
            elif not self.checked_all:
                if self.config.random_work_steal_search:
                    self.work_search_walk_random()
                else:
                    self.work_search_walk()

    def on_complete(self):
        """Complete the task and update accounting."""

        # If work was found, look at own queue
        if self.work_found:
            self.work_steal()
            logging.debug("Setting state to PROCESS")
            self.thread.work_search_state.set_state(WorkSearchState.PROCESS)
            self.thread.successful_ws_time += self.service_time

        # If no work found and completed minimum search time, proceed to next step
        else:
            logging.debug("Setting state to POLL")
            self.thread.work_search_state.set_state(WorkSearchState.POLL)
            self.thread.unsuccessful_ws_time += self.service_time

    def check_sibling(self):
        """Check sibling thread for work."""
        self.start_work_steal_check(self.thread.sibling.queue)

    def work_search_walk_random(self):
        """Randomly select queues to check for work."""
        # Select a random thread to steal from
        if self.config.WORK_STEAL_CHOICES > 1:
            sample_len = (
                self.config.WORK_STEAL_CHOICES
                if len(self.to_search) >= self.config.WORK_STEAL_CHOICES
                else len(self.to_search)
            )
            choices = random.sample(self.to_search, sample_len)
            # Choose the queue with longest queue or oldest task
            choice = choices[0]
            for option in choices:
                self.to_search.remove(option)
                if (
                    self.state.queues[option].current_delay()
                    > self.state.queues[choice].current_delay()
                    or self.thread.queue.id == choice
                ):
                    choice = option
        else:
            choice = random.choice(self.to_search)
            self.to_search.remove(choice)

        if len(self.to_search) == 0 or (
            len(self.to_search) == 1 and self.to_search[0] == self.thread.queue.id
        ):
            self.checked_all = True

        # Use permutation of queues to ensure that allocation policy is not causing clustering in search
        remote = self.state.queues[choice]

        # Skip over ones that were already checked (assumes sibling is not first search)
        if remote.id == self.thread.queue.id and not self.checked_all:
            self.work_search_walk_random()

        # Otherwise, begin process to check if you can steal from it
        else:
            self.start_work_steal_check(remote)

    def work_search_walk(self):
        """Iterate through queues to try to find work to steal."""
        # Select a random thread to steal from then walk through all
        self.search_index += 1
        self.search_index %= self.config.num_worker_queues

        # If back at original index, completed search
        if self.search_index == self.original_search_index:
            self.checked_all = True

        # Use permutation of queues to ensure that allocation policy is not causing clustering in search
        remote = self.state.rx_queues[self.config.WS_PERMUTATION[self.search_index]]

        # Skip over ones that were already checked
        if remote.id == self.thread.queue.id or (
            self.config.ws_sibling_first
            and self.thread.sibling is not None
            and remote.id == self.thread.sibling.queue.id
        ):
            self.work_search_walk()

        # Otherwise, begin to check if you can steal from it
        else:
            self.start_work_steal_check(remote)

    def start_work_steal_check(self, remote):
        """Add to service time the amount required to check another queue and set it as the remote candidate."""
        logging.debug("Start work steal check...")
        self.add_time(self.config.WORK_STEAL_CHECK_TIME)
        self.candidate_remote = remote

    def start_work_steal(self):
        logging.debug("Start work steal...")
        """Add to service time the amount required to work steal."""
        self.add_time(self.config.WORK_STEAL_TIME)

    def descriptor(self):
        remote_id = self.remote.id if self.remote is not None else None
        return "Work Stealing Task (arrival {}, thread {}, remote {})".format(
            self.arrival_time, self.thread.id, remote_id
        )

class NetworkPollTask(Task):
    """Task to run network stack to poll"""
    def __init__(self, thread, config, state):
        super().__init__(config.NETWORK_POLL_TIME, state.timer.get_time(), config, state)
        self.thread = thread
        self.is_productive = True
        self.is_overhead = False
    
    def on_complete(self):
        # Add TX task if finish queue is not empty
        if self.thread.core.tx_queue.work_available() is True:
            logging.debug("Remain {} tasks in TX queue".format(self.thread.core.tx_queue.work_remained()))
            batch = self.thread.core.tx_queue.work_remained()
            tx_task = NetworkTxTask(self.thread, batch, self.config, self.state)
            self.thread.queue.enqueue(tx_task)

        # Poll HW queue 
        # 1. Infinite burst size
        num_recv = 0
        while self.state.task_number[self.thread.id] < len(self.state.tasks[self.thread.id]) and \
                self.state.tasks[self.thread.id][self.state.task_number[self.thread.id]].arrival_time <= self.state.timer.get_time():
            task = self.state.tasks[self.thread.id][self.state.task_number[self.thread.id]]
            # Enqueue tasks into network queue to be received
            rx_task = NetworkRxTask(self.thread, task, self.config, self.state)
            self.thread.queue.enqueue(rx_task)
            logging.debug("[HW RX]: {} onto network receive queue".format(task))
            self.state.task_number[self.thread.id] += 1
            num_recv += 1

        if num_recv > 0:
            logging.debug("Receive {} tasks".format(num_recv))

        if self.thread.queue.work_available():
            self.thread.work_search_state.set_state(WorkSearchState.PROCESS)
        else:
            if self.config.work_stealing_enabled is True:
                self.thread.work_search_state.set_state(WorkSearchState.STEAL)
            else:
                self.thread.work_search_state.set_state(WorkSearchState.POLL)

class NetworkRxTask(Task):
    def __init__(self, thread, task, config, state):
        super().__init__(config.NETWORK_RX_TIME, state.timer.get_time(), config, state)
        self.thread = thread
        self.is_productive = True
        self.is_overhead = False
        self.task = task

    def on_complete(self):
        # Add to worker queue
        self.thread.core.rx_queue.enqueue(self.task)
        # Leave Hardware Queue and enter Software Queue
        self.task.enter_sw_queue = self.state.timer.get_time()
        self.state.complete_rx += 1
        logging.debug("Task: {} is received... rx: {}, tx: {}".format(self.task, self.state.complete_rx, self.state.complete_tx))
        if self.thread.queue.work_available() is False:
            if self.thread.core.rx_queue.work_available() is False:
                if self.config.work_stealing_enabled is True:
                    self.thread.work_search_state.set_state(WorkSearchState.STEAL)
                else:
                    self.thread.work_search_state.set_state(WorkSearchState.POLL)
            else:
                self.thread.work_search_state.set_state(WorkSearchState.YIELD)

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
        while self.thread.core.tx_queue.work_available() is True:
            logging.debug("Remain {} tasks".format(self.thread.core.tx_queue.work_remained()))
            task = self.thread.core.tx_queue.dequeue()
            logging.debug("Task: {} is being transmitted... rx: {}, tx: {}".format(task, self.state.complete_rx, self.state.complete_tx))
            # Leave Hardware Queue and enter Software Queue
            task.leave_hw_queue = self.state.timer.get_time()
            self.state.complete_tx += 1
        if self.thread.queue.work_available() is False:
            if self.thread.core.rx_queue.work_available() is False:
                if self.config.work_stealing_enabled is True:
                    self.thread.work_search_state.set_state(WorkSearchState.STEAL)
                else:
                    self.thread.work_search_state.set_state(WorkSearchState.POLL)
            else:
                self.thread.work_search_state.set_state(WorkSearchState.YIELD)

class ThreadSwitchTask(Task):
    def __init__(self, thread, next, config, state):
        super().__init__(config.THREAD_SWITCH_TIME, state.timer.get_time(), config, state)
        self.curr_thread = thread
        self.next_thread = next
        self.is_productive = False
        self.is_overhead = True

    def on_complete(self):
        # Reset the work search state of previous thread
        self.curr_thread.work_search_state.reset()
        logging.debug("Current thread {} state: {}".format(self.curr_thread.__class__, self.curr_thread.work_search_state))

        # Set new current running thread
        self.curr_thread.core.put_prev_task(self.curr_thread)
        self.curr_thread.core.set_next_task(self.next_thread)
        self.curr_thread.core.context_switch += 1

class PreemptionTask(Task):
    """Preemption task"""
    def __init__(self, thread, config, state):
        super().__init__(config.PREEMPTION_TIME, state.timer.get_time(), config, state)
        self.thread = thread
        self.is_productive = False
        self.is_overhead = True
        
    def on_complete(self):
        self.thread.core.preemption += 1

class QueueCheckTask(Task):
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
            self.thread.work_search_state.advance()

        # If work is available, take it
        elif self.thread.queue.work_available():
            self.thread.current_task = self.thread.queue.dequeue()
            self.thread.current_task.last_sched = self.state.timer.get_time()
            logging.debug("[DEQUEUE]: {} from queue".format(self.thread.current_task))
            self.thread.queue.unlock(self.thread.id)

        # If no work and marked to return to a work steal task, do so
        elif self.return_to_work_steal:
            self.thread.current_task = self.ws_task

        # Otherwise, advance state
        else:
            if self.thread.core.rx_queue.work_available() is False:
                if self.config.work_stealing_enabled is True:
                    self.thread.work_search_state.set_state(WorkSearchState.STEAL)
                else:
                    self.thread.work_search_state.set_state(WorkSearchState.POLL)
            else:
                self.thread.work_search_state.set_state(WorkSearchState.YIELD)

    def descriptor(self):
        return "Local Queue Task (arrival {}, thread {})".format(
            self.arrival_time, self.thread.id
        )
