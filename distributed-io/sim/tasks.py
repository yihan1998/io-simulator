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
        self.front_task_time = 0
        self.is_idle = False
        self.last_sched = None
        self.is_productive = True

        self.original_queue = None
        self.requeue_time = None

        self.counter = 0
        self.preempted = False

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
        if self.time_left == self.service_time:
            self.start_time = self.state.timer.get_time()
            self.last_sched = self.state.timer.get_time()

        self.time_left -= time_increment

        # Any processing that must be done with the decremented timer but before the time left is checked
        self.process_logic()

        # print("\t+ Service time: %d, left time: %d, start time: %d, last sched: %d, curr: %d" % 
        #     (self.service_time, self.time_left, self.start_time, self.last_sched, self.state.timer.get_time()))

        # If preemption enabled, check if the task has been preempted
        if (
            self.config.preempt_enabled
            and type(self) == Task
            and self.time_left > 0
            and preempted
        ):
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

        self.state.tx_batch += 1

        logging.debug("Task complete! TX batch: %d" % self.state.tx_batch)

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
            self.time_in_system(),
            self.service_time,
            self.preempt_count,
            self.original_queue,
            self.total_queue,
            self.queue_checks,
            self.front_task_time,
            self.requeue_wait_time(),
        ]
        stats = [str(x) for x in stats]
        return stats

    @staticmethod
    def get_stat_headers(config):
        headers = [
            "Arrival Time",
            "Time in System",
            "Request Service Time",
            "Preempt Count", 
            "Original Queue",
            "Queue Length",
            "Total Queue Length",
            "Queue Checks",
            "Time Left of Task Ahead",
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

class NetworkRxTask(Task):
    """Task to run network stack to receive packets
    Dequeue from RX queue and enqueue to task queue"""
    def __init__(self, time, arrival_time, config, state):
        super().__init__(config.NETWORK_RX_TIME, state.timer.get_time(), config, state)
        self.task = Task(time, arrival_time, config, state)
        self.is_productive = False
        self.is_overhead = True

    def process(self, time_increment=1, stop_condition=None, preempted=False):
        """Process the task for given time step.
        :param time_increment: Time step.
        :param stop_condition: Additional condition that must be met for the task to complete other than no more time
        left.
        """
        if self.time_left == self.service_time:
            self.start_time = self.state.timer.get_time()
            self.last_sched = self.state.timer.get_time()

        self.time_left -= time_increment

        # Any processing that must be done with the decremented timer but before the time left is checked
        self.process_logic()

        # If no more time left and stop condition is met, complete the task
        if self.time_left <= 0 and (stop_condition is None or stop_condition()):
            self.complete = True
            self.completion_time = self.state.timer.get_time()
            self.on_complete()

    def on_complete(self):
        self.queue.enqueue(self.task, set_original=True)

class NetworkTxTask(Task):
    """Task to run network stack to transmit packets"""
    def __init__(self, thread, config, state):
        super().__init__(config.NETWORK_TX_TIME, state.timer.get_time(), config, state)
        self.thread = thread
        self.is_productive = False
        self.is_overhead = True

    def on_complete(self):
        """Complete the task and do any necessary accounting."""
        # Want to track how many vanilla tasks get completed
        logging.debug("TX count: %d, batch: %d" % (self.state.tx_count, self.state.tx_batch))
        self.state.tx_count += self.state.tx_batch
        self.state.tx_batch = 0

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

        # If no work stealing and there's nothing to get, start spin
        if (
            config.LOCAL_QUEUE_CHECK_TIME == 0
            and not (self.thread.queue.work_available() or self.locked_out)
        ):
            self.service_time = 1
            self.time_left = 1
            self.is_idle = True

    def on_complete(self):
        """Grab new task from queue if available."""
        # If locked out, just advance to next state
        if self.locked_out:
            self.thread.work_search_state.advance()

        # If work is available, take it
        elif self.thread.queue.work_available():
            self.thread.current_task = self.thread.queue.dequeue()
            self.thread.queue.unlock(self.thread.id)
            self.thread.work_search_state.reset()

            if self.thread.last_allocation is not None:
                self.state.alloc_to_task_time += (
                    self.state.timer.get_time() - self.thread.last_allocation
                )
                self.thread.last_allocation = None

        # If no work and marked to return to a work steal task, do so
        elif self.return_to_work_steal:
            self.thread.current_task = self.ws_task

        # Otherwise, advance state
        else:
            self.thread.work_search_state.advance()

    def descriptor(self):
        return "Local Queue Task (arrival {}, thread {})".format(
            self.arrival_time, self.thread.id
        )

class PreemptionTask(Task):
    """Preemption task"""
    def __init__(self, thread, config, state):
        super().__init__(config.PREEMPTION_TIME, state.timer.get_time(), config, state)
        self.thread = thread
        self.is_productive = False
        self.is_overhead = True
        
    def on_complete(self):
        pass

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

        logging.debug(
            "Thread {} work stealing from queue {}".format(self.thread.id, remote.id)
        )
        return True

    def work_steal(self):
        """Steal work from remote queue.
        Takes the first half of tasks from the remote queue and adds to the front of local queue.
        """
        self.state.overall_steal_count += 1

        queue_length = self.remote.length()

        # Avoid inverting the order of stolen tasks (stolen enqueues go to front of queue)
        stolen_tasks = []
        for i in range(math.ceil(queue_length / 2)):
            stolen_tasks.insert(0, self.remote.dequeue())
        for task in stolen_tasks:
            self.thread.queue.enqueue(task, stolen=True)

        self.remote.unlock(self.thread.id)

class WorkStealTask(AbstractWorkStealTask):
    """Task to attempt to steal work from other queues."""

    def __init__(self, thread, config, state):
        super().__init__(thread, None, config, state)
        self.state.work_steal_tasks += 1
        self.original_search_index = (
            self.choose_first_queue()
            if self.config.two_choices
            else int(random.uniform(0, self.config.num_queues))
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
        if num_choices >= self.config.num_queues:
            choices = list(range(0, self.config.num_queues))
        else:
            choices = []
            for i in range(num_choices):
                choices.append(int(random.uniform(0, self.config.num_queues)))

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

    def process(self, time_increment=1, stop_condition=None, preempt_timer=None):
        """Process task and update work steal accounting."""
        if not self.is_zero_duration():
            self.thread.work_stealing_time += time_increment
            if any(q.work_available() for q in self.state.queues):
                self.thread.non_work_conserving_time += time_increment
            if self.config.ws_self_checks:
                self.local_check_timer -= time_increment
        super().process(time_increment=time_increment, stop_condition=self.is_done)

    def delay_flag_check(self):
        """Check if the thread has a work steal flag it should respond to. If it does, take that task."""
        if (
            self.config.delay_flagging_enabled
            and self.thread.work_steal_flag is not None
        ):
            self.thread.current_task = FlagStealTask(
                self.thread, return_to_ws_task=self
            )
            return True
        return False

    def process_logic(self):
        """Search other queues for work to steal."""

        # Do a check of the thread's own queue occasionally
        if (
            not self.work_found
            and self.config.ws_self_checks
            and self.local_check_timer <= 0
        ):
            self.local_check_timer = self.config.LOCAL_QUEUE_CHECK_TIMER
            self.thread.current_task = QueueCheckTask(
                self.thread, self.config, self.state, return_to_ws_task=self
            )

        # Try to find work
        elif not self.work_found and self.time_left <= 0:  # Forces sequential checks
            # Check current candidate
            if self.check_can_work_steal(self.candidate_remote):
                self.work_found = True
                self.remote = self.candidate_remote
                self.start_work_steal()

            # If can't steal, do a flag check (if enabled)
            elif self.delay_flag_check():
                return

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
            self.thread.work_search_state.reset()
            self.thread.successful_ws_time += self.service_time

        # If not enough time has been spent looking for work, start the process over again
        elif (
            self.state.timer.get_time()
            - self.thread.work_search_state.search_start_time
        ) + 1 < self.config.MINIMUM_WORK_SEARCH_TIME:
            self.thread.work_search_state.reset(clear_start_time=False)
            self.thread.unsuccessful_ws_time += self.service_time

            # Need some way to spend time if checking for work has no overhead <- should this even be a possible config?
            if (
                self.config.WORK_STEAL_TIME == 0
                and self.config.WORK_STEAL_CHECK_TIME == 0
                and self.config.LOCAL_QUEUE_CHECK_TIME == 0
            ):
                self.thread.current_task = WorkSearchSpin(self.thread)

        # If no work found and completed minimum search time, proceed to next step
        else:
            self.thread.work_search_state.advance()
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
        self.search_index %= self.config.num_queues

        # If back at original index, completed search
        if self.search_index == self.original_search_index:
            self.checked_all = True

        # Use permutation of queues to ensure that allocation policy is not causing clustering in search
        remote = self.state.queues[self.config.WS_PERMUTATION[self.search_index]]

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
        self.add_time(self.config.WORK_STEAL_CHECK_TIME)
        self.candidate_remote = remote

    def start_work_steal(self):
        """Add to service time the amount required to work steal."""
        self.add_time(self.config.WORK_STEAL_TIME)

    def descriptor(self):
        remote_id = self.remote.id if self.remote is not None else None
        return "Work Stealing Task (arrival {}, thread {}, remote {})".format(
            self.arrival_time, self.thread.id, remote_id
        )