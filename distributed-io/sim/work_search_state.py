#!/usr/bin/env python
"""Maintains current work search state of a core."""


class WorkSearchState:
    """Status of a thread in the work search process."""

    POLL = 0
    PROCESS = 1
    STEAL = 2
    YIELD = 3

    def __init__(self, config, state):
        self._state = self.POLL
        self.config = config
        self.sim_state = state
        self.search_start_time = None

    def set_state(self, state):
        self._state = state

    def reset(self, clear_start_time=True):
        """Reset state to first local queue check and optionally reset the timer for current search."""
        self._state = self.POLL
        if clear_start_time:
            self.search_start_time = None

    def set_start_time(self):
        """Start timer for duration of current work search cycle."""
        if self.search_start_time is None:
            self.search_start_time = self.sim_state.timer.get_time()

    def is_active(self):
        """Returns true if core is not parked or allocating."""
        return self._state != self.LOCAL_THEAD_SWITCH

    def __eq__(self, other):
        return self._state == other

    def __str__(self):
        if self._state == self.POLL:
            return "Replenishing local queue"
        elif self._state == self.PROCESS:
            return "Process local queue"
        elif self._state == self.STEAL:
            return "Stealing work remotely"
        elif self._state == self.YIELD:
            return "Switching thread locally"
        else:
            return "Unknown state"
