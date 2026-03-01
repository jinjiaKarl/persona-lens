import subprocess
import time

CAMOFOX_IMAGE = "camofox-browser:latest"

_started_container_id: str | None = None


def ensure_camofox_running() -> None:
    """Start camofox-browser container in background if not already running."""
    global _started_container_id
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"ancestor={CAMOFOX_IMAGE}", "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            print(f"Starting {CAMOFOX_IMAGE} container...")
            run_result = subprocess.run(
                ["docker", "run", "-d", "--rm", "-p", "9377:9377", CAMOFOX_IMAGE],
                capture_output=True, text=True, check=True, timeout=15,
            )
            _started_container_id = run_result.stdout.strip()
            time.sleep(2)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Warning: could not ensure camofox-browser is running: {e}", flush=True)


def stop_camofox_if_started() -> None:
    """Stop the camofox-browser container if it was started by this process."""
    global _started_container_id
    if not _started_container_id:
        return
    try:
        subprocess.run(
            ["docker", "stop", _started_container_id],
            capture_output=True, timeout=10,
        )
        _started_container_id = None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Warning: could not stop camofox-browser container: {e}", flush=True)
