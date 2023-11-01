#!/usr/bin/env python
"""Maintains current work search state of a core."""


class WorkSearchState:
    """Status of a thread in the work search process."""

    LOCAL_QUEUE_FIRST_CHECK = 0
    WORK_STEAL_CHECK = 1
    LOCAL_QUEUE_FINAL_CHECK = 2

    def __init__(self, config, state):
        self._state = self.LOCAL_QUEUE_FIRST_CHECK
        self.config = config
        self.sim_state = state
        self.search_start_time = None

    def advance(self):
        """Move to the next state (stays in local queue first check if work stealing is disabled)."""
        self._state = (self._state + 1) if self._state < self.LOCAL_QUEUE_FINAL_CHECK else self.LOCAL_QUEUE_FINAL_CHECK
        if not self.config.work_stealing_enabled:
            self._state = self.LOCAL_QUEUE_FIRST_CHECK

    def reset(self, clear_start_time=True):
        """Reset state to first local queue check and optionally reset the timer for current search."""
        self._state = self.LOCAL_QUEUE_FIRST_CHECK
        if clear_start_time:
            self.search_start_time = None

    def set_start_time(self):
        """Start timer for duration of current work search cycle."""
        if self.search_start_time is None:
            self.search_start_time = self.sim_state.timer.get_time()

    def __eq__(self, other):
        return self._state == other

    def __str__(self):
        if self._state == self.LOCAL_QUEUE_FIRST_CHECK:
            return "Checking local queue (first check)"
        elif self._state == self.WORK_STEAL_CHECK:
            return "Attempting to work steal"
        elif self._state == self.LOCAL_QUEUE_FINAL_CHECK:
            return "Checking local queue (last check)"
        else:
            return "Unknown state"
