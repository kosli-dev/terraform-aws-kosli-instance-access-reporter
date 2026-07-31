"""Put the lambda source directories on the path, as they are inside the zip."""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))

for _path in (
    os.path.join(_ROOT, "deployment"),
    os.path.join(_ROOT, "deployment", "instance-access-src"),
):
    if _path not in sys.path:
        sys.path.insert(0, _path)
