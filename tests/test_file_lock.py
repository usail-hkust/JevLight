import pytest

from scripts.file_lock import lock_exclusive


def test_nonblocking_lock_rejects_a_second_file_handle(tmp_path):
    path = tmp_path / "exclusive.lock"
    with path.open("a+b") as first:
        lock_exclusive(first, nonblocking=True)
        with path.open("a+b") as second:
            with pytest.raises(BlockingIOError):
                lock_exclusive(second, nonblocking=True)
