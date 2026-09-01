"""Makes the device modules importable.

device/ is copied to the root of the Presto's filesystem, so its modules
import each other by bare name. The tests need the same path shape.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "device"))
