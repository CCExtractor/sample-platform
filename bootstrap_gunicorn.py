import subprocess

from os import path

current_dir = path.dirname(path.abspath(__file__))

# Arguments to start gunicorn
args = [
    "gunicorn", "-w", "4", "--daemon", "--pid", "gunicorn.pid", "-b",
    "unix:sampleplatform.sock", "-m", "007", "-g", "www-data", "-u",
    "root",
    "--chdir=%s" % current_dir, "--log-level", "debug",
    "--access-logfile", "%s/logs/access.log" % current_dir,
    "--capture-output", "--log-file", "%s/logs/error.log" % current_dir,
    "run:app"
]

subprocess.Popen(args)
