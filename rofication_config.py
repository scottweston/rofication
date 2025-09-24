import logging
import os
import tempfile

import jsonpickle

DEFAULT_SOCKET_FILENAME = "daemon.sock"


def _config_path():
    home = os.path.expanduser("~")
    return os.path.join(home, ".config", "rofication", "config.json")


def load_config():
    """Load the user configuration file if it exists."""
    path = _config_path()
    try:
        with open(path, "r") as handle:
            data = jsonpickle.decode(handle.read())
            if isinstance(data, dict):
                return data
            logging.warning("Config file %s did not contain a dictionary; ignoring", path)
    except FileNotFoundError:
        logging.debug("Config file %s not found; using defaults", path)
    except Exception as exc:
        logging.warning("Failed to load config file %s: %s", path, exc)
    return {}


def _prepare_directory(directory, set_mode=True):
    if not directory:
        return
    os.makedirs(directory, mode=0o700, exist_ok=True)
    if set_mode:
        try:
            os.chmod(directory, 0o700)
        except (PermissionError, NotADirectoryError, OSError):
            pass


def resolve_socket_path(config=None, ensure_dir=False):
    """Resolve the path to the Unix domain socket used for IPC."""
    config = config or {}
    raw_path = config.get("socket_path")
    if raw_path:
        socket_path = os.path.abspath(os.path.expanduser(raw_path))
        if ensure_dir:
            directory = os.path.dirname(socket_path)
            try:
                _prepare_directory(directory)
            except Exception as exc:
                logging.error(
                    "Failed to prepare configured socket directory %s: %s", directory, exc
                )
                raise
        return socket_path

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    candidates = []
    if runtime_dir and os.path.isdir(runtime_dir):
        candidates.append((os.path.join(runtime_dir, "rofication"), True))
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "rofication")
    candidates.append((cache_dir, True))

    for directory, set_mode in candidates:
        socket_path = os.path.join(directory, DEFAULT_SOCKET_FILENAME)
        if ensure_dir:
            try:
                _prepare_directory(directory, set_mode=set_mode)
            except Exception as exc:
                logging.debug(
                    "Failed to prepare socket directory %s: %s", directory, exc
                )
                continue
        return socket_path

    fallback_path = os.path.join(
        tempfile.gettempdir(), f"rofication-{os.getuid()}.sock"
    )
    if ensure_dir:
        fallback_dir = os.path.dirname(fallback_path)
        try:
            _prepare_directory(fallback_dir, set_mode=False)
        except Exception:
            pass
    return fallback_path
