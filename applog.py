"""
File logging.

The app is distributed to strangers who cannot be walked through a debugger,
and the only error surface used to be a truncated line in a queue row. A bug
report of "it doesn't fetch cards" was unactionable because nothing recorded
*why*. This writes a log next to the app so a report can carry a file.

Kept deliberately small: one rotating file, no console handler (the app is
built windowed, so there is no console to write to), and hooks that catch what
would otherwise vanish - unhandled exceptions on the main thread and in worker
threads both used to disappear silently.
"""

import logging
import logging.handlers
import platform
import sys
import threading

from config import ROOT

LOG_PATH = ROOT / "cardwright.log"

# Small on purpose: this is meant to be attached to a bug report, not archived.
_MAX_BYTES = 512 * 1024
_BACKUPS = 2

log = logging.getLogger("cardwright")

_ready = False


def setup():
    """Attach the file handler. Safe to call more than once."""
    global _ready
    if _ready:
        return LOG_PATH

    log.setLevel(logging.DEBUG)
    try:
        handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=_MAX_BYTES, backupCount=_BACKUPS,
            encoding="utf-8")
    except OSError:
        # A read-only install directory must not stop the app from running.
        _ready = True
        return LOG_PATH

    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    _ready = True

    _install_hooks()
    _log_environment()
    return LOG_PATH


def _log_environment():
    from version import APP_VERSION
    log.info("=" * 60)
    log.info("Cardwright %s starting", APP_VERSION)
    log.info("Python %s | %s", sys.version.split()[0], platform.platform())
    log.info("Frozen: %s | Root: %s", getattr(sys, "frozen", False), ROOT)


def _install_hooks():
    """Route crashes into the log instead of nowhere."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        log.critical("Unhandled exception",
                     exc_info=(exc_type, exc, tb))
        previous(exc_type, exc, tb)

    sys.excepthook = hook

    # Worker threads have their own hook; without it a crash inside a
    # download or upscale thread is invisible.
    def thread_hook(args):
        log.critical("Unhandled exception in thread %s",
                     args.thread.name if args.thread else "?",
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = thread_hook
