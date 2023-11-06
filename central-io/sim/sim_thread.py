import logging
from tasks import (
    Task,
    LocalQueueCheckTask,
    GlobalQueueCheckTask,
    PreemptionTask,
    NetworkPollTask,
    NetworkRxTask,
    NetworkTxTask,
)

class Thread:
    """Simulated user-level scheduler"""

    def __init__(self, given_core, given_queue, identifier, config, state):
        self.core = given_core
        self.queue = given_queue
        self.id = identifier
        self.preemption_timer = config.PREEMPTION_ITVL
        self.current_task = None

        self.net_tx_queued = False

        self.time_busy = 0
        self.task_time = 0
        self.network_time = 0
        self.preempt_time = 0

        self.config = config
        self.state = state

    def total_time(self):
        """Return total time spent on tasks, preemption and network."""
        return (
            self.task_time
            + self.network_time
            + self.preemption_time
        )

    def is_busy(self, search_spin_idle=False):
        """Return true if the thread has any task."""
        return self.current_task is not None

    def schedule(self, time_increment=1):
        """Determine how to spend the thread's time."""

        # Work on current task if there is one
        if self.is_busy():
            # Only non-new tasks should use the time_increment (new ones did not exist before this cycle)
            self.process_task(time_increment=time_increment)

        elif type(self.current_task) == PreemptionTask or self.current_task is None:
            self.current_task = GlobalQueueCheckTask(self, self.config, self.state)
            self.process_task()

    def process_task(self, time_increment=1):
        """Process the current task for the given amount of time."""
        initial_task = self.current_task

        # print("Process task ", self.current_task.__class__)

        # Process the task as specified by its type
        self.current_task.process(
            time_increment=time_increment,
            stop_condition=None,
            preempt_timer=self.preemption_timer,
        )

        # print("Current task: ", self.current_task.__class__)

        # If completed, empty current task
        if self.current_task.complete:
            self.current_task = None

        # Or if task was preempted, requeue it
        elif type(self.current_task) == Task and self.current_task.preempted:
            # Add current task to the back of the local queue
            self.current_task.preempted = False
            self.queue.enqueue(self.current_task, requeued=True)
            # Set the current task to PreemptionTask
            self.current_task = PreemptionTask(self, self.config, self.state)
            # Increment preemption counter
            self.state.preemption_count += 1

        # If the task just completed took no time, schedule again
        if initial_task.is_zero_duration():
            self.schedule(time_increment=time_increment)

        # Otherwise, account for the time spent
        else:
            if initial_task.preempted:
                time_increment -= 1

            if not initial_task.is_idle:
                self.time_busy += time_increment

            if initial_task.is_productive:
                self.task_time += time_increment

            elif type(initial_task) == PreemptionTask:
                self.preemption_time += time_increment

            # print("\t\tBusy: %d, network: %d, preemption: %d" % (self.time_busy, self.network_time, self.preemption_time))

    def get_stats(self):
        stats = [
            self.id,
            self.__class__,
            self.time_busy,
            self.task_time,
            self.network_time,
            self.preempt_time,
        ]
        stats = [str(x) for x in stats]
        return stats

    @staticmethod
    def get_stat_headers(config):
        headers = [
            "Thread ID",
            "Type",
            "Busy Time",
            "Task Time",
            "Network Time",
            "Preempt Time",
        ]
        return headers

    def __str__(self):
        if self.is_busy():
            return "Thread {} (queue {}): busy on {}".format(
                self.id, self.queue.id, self.current_task
            )
        else:
            return "Thread {} (queue {}): idle".format(self.id, self.queue.id)

    def __repr__(self):
        return str(self)

class WorkerThread(Thread):
    def __init__(self, given_core, given_queue, finish_queue, identifier, config, state):
        super().__init__(given_core, given_queue, identifier, config, state)
        self.finish_queue = finish_queue

    def process_task(self, time_increment=1):
        """Process the current task for the given amount of time."""
        initial_task = self.current_task
        preempt = False

        logging.debug("preempt timer on: {}, start: {}, task {}, remain: {}"
                      .format(self.core.preempt_timer_on, self.core.preempt_timer_start, self, self.current_task.time_left))

        if (self.config.preempt_enabled
            and self.core.preempt_timer_on
            and self.state.timer.get_time() - self.core.preempt_timer_start >= self.config.PREEMPTION_ITVL):
            preempt = True
            logging.debug("Preempting current task, remain: {}".format(self.current_task.time_left))

        # Process the task as specified by its type
        self.current_task.process(
            time_increment=time_increment,
            stop_condition=None,
            preempted=preempt
        )

        # If completed, empty current task
        if self.current_task.complete:
            if type(self.current_task) == Task:
                self.finish_queue.enqueue(self.current_task)
                self.current_task.leave_sw_queue = self.state.timer.get_time()
                self.core.preempt_timer_on = False
            self.current_task = None

        elif self.current_task.preempted:
            # Add current task to the back of the local queue
            # TODO: Should we schedule the Network thread before continue processing the preempted task?
            self.core.preempt_timer_on = False
            self.current_task.preempted = False
            self.queue.enqueue(self.current_task, requeued=True)
            # Set the current task to PreemptionTask
            self.current_task = PreemptionTask(self, self.config, self.state)

        # If the task just completed took no time, schedule again
        if initial_task.is_zero_duration():
            self.schedule(time_increment=time_increment)

        # Otherwise, account for the time spent
        else:
            if initial_task.preempted:
                time_increment -= 1

            if not initial_task.is_idle:
                self.time_busy += time_increment

            if initial_task.is_productive:
                self.task_time += time_increment

            if initial_task.is_overhead:
                self.preempt_time += time_increment

    def schedule(self, time_increment=1):
        """Determine how to spend the thread's time."""
        logging.debug("Remain {} task in queue".format(self.queue.work_remained()))
        # Work on current task if there is one
        if self.is_busy():
            # Only non-new tasks should use the time_increment (new ones did not exist before this cycle)
            self.process_task(time_increment=time_increment)

        # Check if there are remaining tasks in current work queue
        elif self.queue.work_available():
            self.current_task = GlobalQueueCheckTask(self, self.config, self.state)
            self.process_task()

class NetworkThread(Thread):
    def __init__(self, given_core, given_queue, finish_queue, identifier, config, state):
        super().__init__(given_core, given_queue, identifier, config, state)
        self.finish_queue = finish_queue

    def process_task(self, time_increment=1):
        initial_task = self.current_task

        # print("Process task ", self.current_task.__class__)

        logging.debug("Task {}, remain: {}".format(self.current_task, self.current_task.time_left))

        # Process the task as specified by its type
        self.current_task.process(
            time_increment=time_increment,
            stop_condition=None,
            preempted=False
        )

        # If completed, empty current task
        if self.current_task.complete:
            self.current_task = None

        # If the task just completed took no time, schedule again
        if initial_task.is_zero_duration():
            self.schedule(time_increment=time_increment)

        # Otherwise, account for the time spent
        else:
            if not initial_task.is_idle:
                self.time_busy += time_increment

            if initial_task.is_productive:
                self.network_time += time_increment

    def schedule(self, time_increment=1):
        """Determine how to spend the thread's time."""
        # Work on current task if there is one
        if self.is_busy():
            # Only non-new tasks should use the time_increment (new ones did not exist before this cycle)
            self.process_task(time_increment=time_increment)

        else:            
            # Check if there are remaining tasks in current work queue
            if self.queue.work_remained():
                self.current_task = LocalQueueCheckTask(self, self.config, self.state)
                self.process_task()

            else:
                self.current_task = NetworkPollTask(self, self.config, self.state)
                self.process_task()