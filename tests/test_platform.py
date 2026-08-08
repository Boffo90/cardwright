"""
The platform branches introduced by the macOS port.

Windows is the distributed build, so these assert the Windows side as well as
the POSIX side and do it from either OS: the config/bootstrap constants are
re-derived with sys.platform patched, and the two runtime dispatches are
driven through the IS_WINDOWS flag their module holds. A contributor working
on a Mac can therefore still catch a branch that was written the wrong way
round.
"""

import importlib
import io
import subprocess
import sys
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image

import bootstrap
import config
import gui
import update
import upscale


@contextmanager
def rederived_as(platform_name):
    """Re-import config/bootstrap as if running on `platform_name`."""
    real = sys.platform
    sys.platform = platform_name
    try:
        yield importlib.reload(config), importlib.reload(bootstrap)
    finally:
        sys.platform = real
        importlib.reload(config)
        importlib.reload(bootstrap)


# --------------------------------------------------------------- engine path

def test_windows_uses_the_exe_and_suppresses_the_console():
    with rederived_as("win32") as (cfg, _):
        assert cfg.IS_WINDOWS
        assert cfg.REALESRGAN_EXE.name == "realesrgan-ncnn-vulkan.exe"
        # CREATE_NO_WINDOW; losing it means a console flashes up per card.
        assert cfg.NO_WINDOW_KWARGS == {"creationflags": 0x08000000}


def test_macos_uses_the_bare_binary_and_no_creationflags():
    with rederived_as("darwin") as (cfg, _):
        assert not cfg.IS_WINDOWS
        assert cfg.REALESRGAN_EXE.name == "realesrgan-ncnn-vulkan"
        # Passing creationflags on POSIX raises ValueError, which would break
        # every upscale and the GPU probe.
        assert cfg.NO_WINDOW_KWARGS == {}


# ------------------------------------------------------------ engine sources

def test_windows_downloads_the_windows_zip_and_the_redistributable():
    with rederived_as("win32") as (_, bs):
        assert bs.ENGINE_ZIP_URL.endswith("-windows.zip")
        assert bs.ENGINE_FILES == ["realesrgan-ncnn-vulkan.exe", "vcomp140.dll"]


def test_macos_downloads_the_macos_zip_and_needs_no_redistributable():
    with rederived_as("darwin") as (_, bs):
        assert bs.ENGINE_ZIP_URL.endswith("-macos.zip")
        # The macOS build links only against system frameworks.
        assert bs.ENGINE_FILES == ["realesrgan-ncnn-vulkan"]


def test_engine_files_and_engine_path_agree():
    """missing_components() looks for ENGINE_FILES; upscale runs REALESRGAN_EXE."""
    for platform_name in ("win32", "darwin"):
        with rederived_as(platform_name) as (cfg, bs):
            assert cfg.REALESRGAN_EXE.name in bs.ENGINE_FILES


def test_model_files_are_the_same_on_both_platforms():
    """Both release zips carry identically named models, so this must not fork."""
    with rederived_as("win32") as (_, bs):
        windows_models = list(bs.MODEL_FILES)
    with rederived_as("darwin") as (_, bs):
        assert list(bs.MODEL_FILES) == windows_models


# ------------------------------------------------------------------- updater

def test_update_check_is_skipped_off_windows(monkeypatch):
    """Releases only carry Windows assets; a Mac must not be offered an .exe."""
    calls = []
    monkeypatch.setattr(update, "IS_WINDOWS", False)
    monkeypatch.setattr(update.requests, "get", _recording_get(calls))
    assert update.check_for_update() is None
    assert calls == [], "the guard should short-circuit before any request"


def test_update_check_still_runs_on_windows(monkeypatch):
    """The guard must not disable the updater on the platform that ships it."""
    calls = []
    monkeypatch.setattr(update, "IS_WINDOWS", True)
    monkeypatch.setattr(update.requests, "get", _recording_get(calls))
    # Reaching the network call at all proves the guard let Windows through;
    # check_for_update swallows RequestException and returns None.
    assert update.check_for_update() is None
    assert len(calls) == 1


def _recording_get(calls):
    def get(*a, **kw):
        calls.append(a)
        raise update.requests.RequestException("no network in tests")
    return get


# --------------------------------------------------------- file manager open

def test_open_folder_uses_startfile_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(gui, "IS_WINDOWS", True)
    seen = []
    # os.startfile only exists on Windows, so it is created for the test.
    monkeypatch.setattr(gui.os, "startfile", seen.append, raising=False)
    monkeypatch.setattr(gui.subprocess, "run", _never_called)
    gui._open_folder(tmp_path)
    assert seen == [tmp_path]


def _never_called(*a, **kw):
    raise AssertionError("should not shell out on Windows")


def test_open_folder_shells_out_to_open_elsewhere(monkeypatch, tmp_path):
    monkeypatch.setattr(gui, "IS_WINDOWS", False)
    seen = []

    def fake_run(cmd, *a, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(gui.subprocess, "run", fake_run)
    gui._open_folder(tmp_path)
    assert seen == [["open", str(tmp_path)]]


def test_open_folder_raises_oserror_when_open_fails(monkeypatch, tmp_path):
    """Callers fall back on OSError, which is what startfile raises."""
    monkeypatch.setattr(gui, "IS_WINDOWS", False)
    monkeypatch.setattr(
        gui.subprocess, "run",
        lambda cmd, *a, **kw: subprocess.CompletedProcess(cmd, 1))
    try:
        gui._open_folder(tmp_path)
    except OSError:
        return
    raise AssertionError("expected OSError")


# ==========================================================================
# The constants above being right is only half of it — these drive the real
# functions and assert the values actually reach the engine, so dropping the
# kwargs or the chmod fails a test instead of passing quietly.
# ==========================================================================

class _FakePopen:
    """Stands in for the engine and records how it was launched."""

    cmd = None
    kwargs = None

    def __init__(self, cmd, **kwargs):
        type(self).cmd = cmd
        type(self).kwargs = kwargs
        # the real engine writes its result to the path after -o
        Image.new("RGB", (8, 8)).save(Path(cmd[cmd.index("-o") + 1]))
        self.stdout = io.StringIO("")
        self.returncode = 0

    def poll(self):
        return 0

    def wait(self):
        return 0


def _run_one_upscale(monkeypatch, tmp_path, no_window_kwargs):
    """Drive upscale() end to end with the engine faked out."""
    engine = tmp_path / "engine"
    engine.write_text("")
    src = tmp_path / "card.png"
    # 744x1040 is large enough to skip the pre-scale branch and small enough
    # that the AI step is not skipped, so execution reaches Popen.
    Image.new("RGB", (744, 1040)).save(src)

    monkeypatch.setattr(upscale, "REALESRGAN_EXE", engine)
    monkeypatch.setattr(upscale, "OUTPUT_FOLDER", tmp_path)
    monkeypatch.setattr(upscale, "NO_WINDOW_KWARGS", no_window_kwargs)
    monkeypatch.setattr(upscale.subprocess, "Popen", _FakePopen)

    upscale.upscale(src, model_label="AnimeVideo v3 x4 (scanned cards)",
                    fit_to_card=False, rename=False)
    return _FakePopen.kwargs


def test_upscale_passes_creationflags_through_on_windows(monkeypatch, tmp_path):
    kwargs = _run_one_upscale(monkeypatch, tmp_path,
                              {"creationflags": 0x08000000})
    assert kwargs["creationflags"] == 0x08000000


def test_upscale_sends_no_creationflags_on_posix(monkeypatch, tmp_path):
    # Passing creationflags here is the ValueError that broke every upscale.
    kwargs = _run_one_upscale(monkeypatch, tmp_path, {})
    assert "creationflags" not in kwargs


def _run_probe(monkeypatch, tmp_path):
    """Drive probe_gpu() with the engine faked out; report how it was called."""
    engine = tmp_path / "engine"
    engine.write_text("")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        Path(cmd[cmd.index("-o") + 1]).write_text("")
        return subprocess.CompletedProcess(cmd, 0, stdout="[0 Test GPU]\n",
                                           stderr="")

    monkeypatch.setattr(bootstrap, "REALESRGAN_EXE", engine)
    monkeypatch.setattr(bootstrap, "TEMP_FOLDER", tmp_path)
    monkeypatch.setattr(bootstrap, "NO_WINDOW_KWARGS",
                        {"creationflags": 0x08000000})
    monkeypatch.setattr(bootstrap, "load_settings", dict)
    monkeypatch.setattr(bootstrap, "save_settings", lambda data: None)
    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    seen["result"] = bootstrap.probe_gpu()
    return seen


def test_probe_gpu_passes_the_kwargs_through(monkeypatch, tmp_path):
    seen = _run_probe(monkeypatch, tmp_path)
    assert seen["kwargs"].get("creationflags") == 0x08000000
    # the GPU name is parsed out of the engine's own banner
    assert seen["result"] == (True, "Test GPU")


# --------------------------------------------------- engine model directory
# The engine resolves -m against the working directory and defaults to a bare
# "models". Left off, it silently finds nothing unless the app happens to have
# been started from its own folder: probing then reports "no compatible Vulkan
# GPU" and persists that, disabling AI on a perfectly good machine.

def _model_dir_from(cmd):
    assert "-m" in cmd, "the engine was not told where the models are"
    return Path(cmd[cmd.index("-m") + 1])


def test_upscale_points_the_engine_at_the_absolute_model_folder(
        monkeypatch, tmp_path):
    _run_one_upscale(monkeypatch, tmp_path, {})
    model_dir = _model_dir_from(_FakePopen.cmd)
    assert model_dir.is_absolute()
    assert model_dir == upscale.MODELS_FOLDER


def test_probe_gpu_points_the_engine_at_the_absolute_model_folder(
        monkeypatch, tmp_path):
    seen = _run_probe(monkeypatch, tmp_path)
    model_dir = _model_dir_from(seen["cmd"])
    assert model_dir.is_absolute()
    assert model_dir == bootstrap.MODELS_FOLDER


class _FakeResponse:
    def __init__(self, payload):
        self.content = payload
        self.headers = {"Content-Length": str(len(payload))}

    def raise_for_status(self):
        pass

    def iter_content(self, chunk):
        yield self.content


@pytest.mark.skipif(sys.platform == "win32",
                    reason="the exec bit is a POSIX concept")
def test_download_all_makes_the_engine_executable(monkeypatch, tmp_path):
    """Without this chmod the downloaded engine simply cannot be spawned."""
    models = tmp_path / "models"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in bootstrap.ENGINE_FILES:
            z.writestr(name, "binary")
        for name in bootstrap.MODEL_FILES:
            z.writestr(f"models/{name}", "weights")

    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "MODELS_FOLDER", models)
    monkeypatch.setattr(bootstrap.requests, "get",
                        lambda url, **kw: _FakeResponse(buf.getvalue()))

    bootstrap.download_all()

    engine = tmp_path / bootstrap.ENGINE_FILES[0]
    assert engine.exists()
    assert engine.stat().st_mode & 0o111, "engine is not executable"
