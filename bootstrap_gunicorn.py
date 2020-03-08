"""starts gunicorn server with appropriate arguments and options in a new process."""

import subprocess
from os import path

current_dir = path.dirname(path.abspath(__file__))

# Arguments to start gunicorn
args = [
    "gunicorn", "-w", "4", "--daemon", "--pid", "gunicorn.pid", "-b", "unix:sampleplatform.sock", "-m", "007",
    "-g", "www-data", "-u", "www-data", f"--chdir={current_dir}", "--log-level", "debug",
    "--access-logfile", f"{current_dir}/logs/access.log", "--capture-output",
    "--log-file", f"{current_dir}/logs/error.log", "run:app"
]

subprocess.Popen(args)
