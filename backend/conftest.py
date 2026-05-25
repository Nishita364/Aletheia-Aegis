"""
Root conftest.py for the backend test suite.

Adds the ``backend/`` directory to ``sys.path`` so that both bare module
imports (``from ml.xxx import ...``) used by the internal modules and
``backend.``-prefixed imports (``from backend.main import create_app``)
used by the integration tests resolve correctly.
"""

import sys
from pathlib import Path

# Insert the backend/ directory at the front of sys.path so that
# ``from ml.xxx import ...`` resolves to backend/ml/xxx.py
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
