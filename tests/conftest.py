import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="mc-test-")
os.environ["MC_DATA"] = _tmp
os.environ["MC_MODE"] = "fake"
os.environ["MC_VIDEO_SIZE"] = "640x360"
