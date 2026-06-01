import os
import select
import subprocess
from typing import Protocol


class _SupportsLogging(Protocol):
    """Structural type accepted by run_cmd — satisfied by logbook.Logger,
    InterceptLogger, and any other object with info/error methods."""
    def info(self, msg: str, /) -> None: ...
    def error(self, msg: str, /) -> None: ...


def run_cmd(command: list[str], logger: _SupportsLogging):
    # For Python children, ensure unbuffered output; harmless for others.
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,   # line-buffered
        env=env,
    )

    # Read both pipes in the *calling* thread rather than spawning reader
    # threads.  This is essential so that Logbook's thread-local handler
    # stack — which holds DBLogHandler — is active when each line is logged.
    # select.select() lets us multiplex both pipes without blocking on either.
    open_fds = {proc.stdout, proc.stderr}
    while open_fds:
        readable, _, _ = select.select(open_fds, [], [])
        for fd in readable:
            if fd is not None:
                line = fd.readline()
                if line:
                    if fd is proc.stdout:
                        logger.info(line.rstrip())
                    else:
                        logger.error(line.rstrip())
                else:
                    # EOF on this pipe — process has closed it.
                    open_fds.discard(fd)

    proc.wait()
    if proc.returncode:
        logger.error(f"Command {command!r} exited with code {proc.returncode}")
        raise subprocess.CalledProcessError(proc.returncode, command)