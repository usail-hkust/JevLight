"""Hold the existing project file lock across the bootstrap's process lifetime."""
import os
from pathlib import Path
import sys

from scripts.file_lock import lock_exclusive

ROOT = Path(__file__).resolve().parents[1]


def launch(arguments):
    path = ROOT / ".local/vision-server.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        try:
            lock_exclusive(lock, nonblocking=True)
        except BlockingIOError:
            raise SystemExit("Another vision download/experiment already owns this project. "
                             "Inspect its log; do not launch a second copy.") from None
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid={os.getpid()}\n".encode())
        lock.flush()
        # POSIX flock ownership survives exec only when its descriptor is inherited.
        os.set_inheritable(lock.fileno(), True)
        env = dict(os.environ, JEVLIGHT_VISION_LOCK_FD=str(lock.fileno()))
        os.execvpe("bash", ["bash", str(ROOT / "scripts/run_vision_server.sh"), *arguments], env)


if __name__ == "__main__":
    launch(sys.argv[1:])
