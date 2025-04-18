import os
import subprocess
import threading
from logbook import Logger

def run_cmd(command: list[str], logger: Logger):
    # for Python children, ensure unbuffered; harmless for others
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,        # universal_newlines=True
        bufsize=1,        # line‑buffering
        env=env,
    )

    def log_stream(stream, log_method):
        for line in stream:
            log_method(line.rstrip())
        stream.close()

    threads = [
        threading.Thread(target=log_stream, args=(proc.stdout, logger.info), daemon=True),
        threading.Thread(target=log_stream, args=(proc.stderr, logger.error), daemon=True),
    ]
    for t in threads:
        t.start()

    returncode = proc.wait()
    for t in threads:
        t.join()

    if returncode:
        logger.error(f"Command {command!r} exited with code {returncode}")
        raise subprocess.CalledProcessError(returncode, command)