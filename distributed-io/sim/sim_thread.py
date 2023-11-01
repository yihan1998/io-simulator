import logging
from work_search_state import WorkSearchState

from tasks import (
    Task,
    QueueCheckTask,
    PreemptionTask,
    NetworkRxTask,
    NetworkTxTask,
)

class Thread:
    """Simulated user-level scheduler"""

    def __init__(self, given_queue, identifier, config, state):
        self.queue = given_queue
        self.id = identifier
        self.work_search_state = WorkSearchState(config, state)
        self.current_task = None

        self.preempted = False

        self.net_tx_queued = False

        self.time_busy = 0
        self.network_time = 0
        self.enqueue_time = 0
        self.requeue_time = 0
        self.task_time = 0
        self.work_steal_wait_time = 0
        self.successful_ws_time = 0
        self.unsuccessful_ws_time = 0
        self.preemption_time = 0

        self.config = config
        self.state = state

    def total_time(self):
        """Return total time spent on tasks, preemption and network."""
        return (
            self.network_time
            + self.preemption_time
            + self.task_time
        )

    def is_busy(self, search_spin_idle=False):
        """Return true if the thread has any task."""
        if search_spin_idle:
            return (
                self.current_task is not None
                and type(self.current_task) != WorkSearchSpin
            )
        return self.current_task is not None

    def schedule(self, time_increment=1):
        """Determine how to spend the thread's time."""

        # Work on current task if there is one
        if self.is_busy():
            # Only non-new tasks should use the time_increment (new ones did not exist before this cycle)
            self.process_task(time_increment=time_increment)

        elif type(self.current_task) == PreemptionTask or self.current_task is None:
            logging.debug("Thread: {}".format(self))
            self.current_task = QueueCheckTask(self, self.config, self.state)
            self.process_task()

        # Try own queue first
        elif self.work_search_state == WorkSearchState.LOCAL_QUEUE_FIRST_CHECK:
            if self.current_task is None:
                self.current_task = QueueCheckTask(self, self.config, self.state)
                self.work_search_state.set_start_time()

            self.process_task()

        # Then try stealing
        elif self.work_search_state == WorkSearchState.WORK_STEAL_CHECK:
            self.current_task = WorkStealTask(self, self.config, self.state)
            self.process_task()

        # Check own queue one last time before parking
        elif self.work_search_state == WorkSearchState.LOCAL_QUEUE_FINAL_CHECK:
            if self.config.delay_flagging_enabled:
                self.delay_flagging()
                if self.work_steal_flag is not None:
                    self.current_task = FlagStealTask(self, self.config, self.state)

            if self.current_task is None:
                self.current_task = QueueCheckTask(self, self.config, self.state)
            self.process_task()

    def process_task(self, time_increment=1):
        """Process the current task for the given amount of time."""
        initial_task = self.current_task

        # print("Process task ", self.current_task.__class__)

        # Process the task as specified by its type
        self.current_task.process(
            time_increment=time_increment,
            stop_condition=None,
            preempted=self.preempted,
        )

        self.preempted = False

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
            logging.debug("Set the current task to PreemptionTask")
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

            elif type(initial_task) == NetworkRxTask or type(initial_task) == NetworkTxTask:
                self.network_time += time_increment

            elif type(initial_task) == PreemptionTask:
                self.preemption_time += time_increment

            # print("\t\tBusy: %d, network: %d, preemption: %d" % (self.time_busy, self.network_time, self.preemption_time))

    def get_stats(self):
        stats = [
            self.id,
            self.time_busy,
            self.task_time,
            self.enqueue_time,
            self.requeue_time,
            self.network_time,
            self.preemption_time,
        ]
        stats = [str(x) for x in stats]
        return stats

    @staticmethod
    def get_stat_headers(config):
        headers = [
            "Thread ID",
            "Busy Time",
            "Task Time",
            "Enqueue Time",
            "Requeue Time",
            "Network Time",
            "Preemption Time",
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