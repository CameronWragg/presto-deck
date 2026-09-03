"""Makes the device modules importable.

device/ is copied to the root of the Presto's filesystem, so its modules
import each other by bare name. The tests need the same path shape.

Every project's device modules live flat under that project's device/, so
two projects can - and do - both have a demo.py. pytest imports all of them
into one interpreter, so whichever project was collected first would
otherwise leave its module cached under the shared name and hand it to the
other project's tests. Claiming sys.path[0] and evicting anything cached
from a different device/ keeps each project's tests looking at its own code.
"""

import os
import sys

DEVICE = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "device")
)
OUR_MODULES = frozenset(
    name[:-3] for name in os.listdir(DEVICE) if name.endswith(".py")
)


def use_our_device_modules():
    while DEVICE in sys.path:
        sys.path.remove(DEVICE)
    sys.path.insert(0, DEVICE)

    for name in list(sys.modules):
        if name not in OUR_MODULES:
            continue
        path = getattr(sys.modules[name], "__file__", None)
        if path and os.path.dirname(os.path.abspath(path)) != DEVICE:
            del sys.modules[name]


use_our_device_modules()
