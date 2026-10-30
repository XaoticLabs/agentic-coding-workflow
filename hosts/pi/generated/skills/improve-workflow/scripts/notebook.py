#!/usr/bin/env python3
"""Generated canonical-script entrypoint; edit the original skill."""
import os
from pathlib import Path
import sys
_workflow_source = (Path(__file__).resolve().parent / '../../../../../../skills/improve-workflow/scripts/notebook.py').resolve()
os.environ['WORKFLOW_HOST'] = 'pi'
if __name__ == '__main__':
    os.execv(sys.executable, [sys.executable, str(_workflow_source), *sys.argv[1:]])
else:
    __file__ = str(_workflow_source)
    sys.path.insert(0, str(_workflow_source.parent))
    exec(compile(_workflow_source.read_bytes(), __file__, 'exec'), globals())
