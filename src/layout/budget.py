"""Bound deterministic search work and allow an explicit wall-clock cancellation."""

from math import isfinite
from time import monotonic


class BudgetExceeded(ValueError):
    pass


class SearchBudget:
    def __init__(self, operations, timeout=None):
        if timeout is not None and (type(timeout) not in (int,float) or not isfinite(timeout) or timeout<=0):
            raise ValueError("Layout timeout must be a positive finite number.")
        self.limit = operations
        self.deadline = None if timeout is None else monotonic() + timeout
        self.operations = 0

    def check(self):
        if self.deadline is not None and monotonic() >= self.deadline:
            raise BudgetExceeded("Layout exceeded its time limit.")

    def step(self, amount=1):
        previous = self.operations
        self.operations += amount
        if self.operations > self.limit:
            raise BudgetExceeded("Layout exceeded its deterministic routing work limit.")
        if previous // 64 != self.operations // 64:
            self.check()
