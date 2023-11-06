import logging

class Core:
    """Simulated core"""

    def __init__(self, identifier, config, state):
        self.id = identifier
        self.config = config
        self.state = state

        self.runqueue = []
        self.all_threads = []
        self.current_thread = None

        self.context_switch = 0
        self.preemption = 0

        self.preempt_timer_on = False
        self.preempt_timer_start = None

    def get_stats(self):
        time_busy = 0
        task_time = 0
        network_time = 0
        preempt_time = 0

        for thread in self.all_threads:
            time_busy += thread.time_busy
            task_time += thread.task_time
            network_time += thread.network_time
            preempt_time += thread.preempt_time

        stats = [
            self.id,
            time_busy,
            task_time,
            network_time,
            preempt_time,
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

    def have_runnable_threads(self):
        """Return whether there are tasks currently in the queue."""
        return len(self.runqueue) > 0

    def create_thread(self, thread):
        self.runqueue.append(thread)
        self.all_threads.append(thread)

    def put_prev_task(self, thread):
        self.runqueue.append(thread)
        self.current_thread = None

    def pick_next_task(self):
        return self.runqueue.pop(0)
    
    def set_next_task(self, thread):
        self.current_thread = thread
    
    def schedule(self):
        if self.current_thread is None:
            next = self.pick_next_task()
            self.set_next_task(next)

        self.current_thread.schedule()
