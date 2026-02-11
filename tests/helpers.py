"""Shared test helper functions."""


def create_sync_flag(flag_file: str) -> None:
    """Write a sync flag file (paused or disabled)."""
    with open(flag_file, "w") as f:
        f.write("1")
