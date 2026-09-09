"""
Choosing where finished cards land.

Asked for by a user who wanted it on a second drive: a card is ~29 MB at
1200 DPI, so a project fills a disk quickly.

The setting is read on every call rather than bound at import, so picking a
new folder takes effect without a restart - and so that an external drive
going missing is noticed rather than baked in at startup.
"""

import pytest

import config


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """A settings file of our own, and a default output folder of our own."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    default = tmp_path / "app-output"
    monkeypatch.setattr(config, "OUTPUT_FOLDER", default)
    return default


# ----------------------------------------------------------- the default

def test_with_nothing_set_it_is_the_app_folder(settings):
    assert config.output_folder() == settings
    assert settings.is_dir()          # made on demand, not assumed to exist


def test_nothing_is_wrong_when_nothing_is_set(settings):
    assert config.output_problem() is None


# ------------------------------------------------------------ choosing

def test_a_chosen_folder_is_used(settings, tmp_path):
    other = tmp_path / "big-drive" / "cards"
    config.set_output_folder(other)
    assert config.output_folder() == other
    assert other.is_dir()             # created, so the first card has a home


def test_it_takes_effect_without_a_restart(settings, tmp_path):
    """The value is read per call. Bound at import, a change would need the
    app closed and reopened to land."""
    first = config.output_folder()
    config.set_output_folder(tmp_path / "elsewhere")
    assert config.output_folder() != first


def test_resetting_goes_back_to_the_app_folder(settings, tmp_path):
    config.set_output_folder(tmp_path / "elsewhere")
    config.set_output_folder(None)
    assert config.output_folder() == settings
    assert config.output_problem() is None


def test_a_blank_setting_is_the_same_as_none(settings):
    config.save_settings({"output_folder": "   "})
    assert config.output_folder() == settings
    assert config.output_problem() is None


# ------------------------------------------- the drive that is not there

@pytest.fixture
def unreachable(tmp_path):
    """A path that genuinely cannot be created, no mocking involved: a folder
    underneath a regular file. Stands in for the drive that is not plugged in,
    and exercises the same OSError."""
    blocker = tmp_path / "not-a-drive"
    blocker.write_bytes(b"")
    return blocker / "cards"


def test_an_unusable_folder_falls_back_rather_than_failing(settings,
                                                           unreachable):
    """The external drive not being plugged in is the case this exists for.
    A card written beside the app beats a card that could not be written."""
    config.set_output_folder(unreachable)
    assert config.output_folder() == settings


def test_and_it_says_which_folder_is_missing(settings, unreachable):
    """Silently writing somewhere else would look like the setting was
    ignored. The GUI shows this once at startup."""
    config.set_output_folder(unreachable)
    assert config.output_problem() == str(unreachable)


def test_the_setting_survives_the_drive_being_away(settings, unreachable):
    """Falling back must not erase the choice: the drive comes back next
    time, and retyping the path then would be daft."""
    config.set_output_folder(unreachable)
    config.output_folder()
    assert config.load_settings().get("output_folder") == str(unreachable)


def test_a_folder_that_exists_but_cannot_be_written_is_also_a_problem(
        settings, tmp_path, monkeypatch):
    """Existing is not the same as usable - a read-only mount passes mkdir
    and then fails on the first card."""
    target = tmp_path / "read-only"
    target.mkdir()
    config.set_output_folder(target)

    real_touch = config.Path.touch

    def no_touch(self, *a, **kw):
        if self.name == ".cardwright-write-test":
            raise OSError("read-only")
        return real_touch(self, *a, **kw)

    monkeypatch.setattr(config.Path, "touch", no_touch)
    assert config.output_folder() == settings
    assert config.output_problem() == str(target)


def test_the_write_test_leaves_nothing_behind(settings, tmp_path):
    target = tmp_path / "cards"
    config.set_output_folder(target)
    config.output_folder()
    assert list(target.iterdir()) == []
