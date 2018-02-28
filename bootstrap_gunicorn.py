import subprocess
from os import path

current_dir = path.dirname(path.abspath(__file__))

# Arguments to start gunicorn
args = [
    "gunicorn", "-w", "4", "--daemon", "--pid", "gunicorn.pid", "-b", "unix:sampleplatform.sock", "-m", "007",
    "-g", "www-data", "-u", "www-data", "--chdir={0}".format(current_dir), "--log-level", "debug",
    "--access-logfile", "{0}/logs/access.log".format(current_dir), "--capture-output",
    "--log-file", "{0}/logs/error.log".format(current_dir), "run:app"
]

subprocess.Popen(args)
