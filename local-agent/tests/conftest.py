"""Test-suite environment.

The HTTP boundary (``security/http_boundary.py``) trusts only loopback Host
names by default. Existing tests drive the app through in-process transports
whose synthetic base URLs use the hosts ``test`` and ``testserver``. Those two
synthetic hosts are added for THIS test process only, through the same
``VECTOR_TRUSTED_HOSTS`` setting an operator would use. Production defaults are
unchanged, and ``test_http_boundary.py`` clears this variable to prove them.

This must run before ``vector_agent.core.config`` is first imported, because the
settings singleton is created at import time.
"""

from __future__ import annotations

import os

os.environ.setdefault("VECTOR_TRUSTED_HOSTS", '["127.0.0.1", "localhost", "test", "testserver"]')
