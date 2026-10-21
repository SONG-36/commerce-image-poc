"""Existing application error contract, shared by planning and the HTTP facade.

Retain the legacy name/status values without importing a transport framework.
"""


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
