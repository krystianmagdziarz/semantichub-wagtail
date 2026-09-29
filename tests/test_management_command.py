import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

COMMAND_MODULE = "semantichub_wagtail.management.commands.semantichub_push_manifest"


def test_command_fails_without_configuration(settings):
    settings.SEMANTICHUB_API_BASE_URL = ""
    settings.SEMANTICHUB_AGENT_TOKEN = ""
    settings.SEMANTICHUB_GOAL_ID = ""
    with pytest.raises(CommandError):
        call_command("semantichub_push_manifest")


def test_command_refuses_plain_http(settings, monkeypatch):
    settings.SEMANTICHUB_API_BASE_URL = "http://example.test"
    settings.SEMANTICHUB_AGENT_TOKEN = "tok"
    settings.SEMANTICHUB_GOAL_ID = "goal-1"
    monkeypatch.setattr(f"{COMMAND_MODULE}.push_manifest", lambda: True)
    with pytest.raises(CommandError, match="https"):
        call_command("semantichub_push_manifest")


def test_command_succeeds_when_push_succeeds(settings, monkeypatch):
    settings.SEMANTICHUB_API_BASE_URL = "https://example.test"
    settings.SEMANTICHUB_AGENT_TOKEN = "tok"
    settings.SEMANTICHUB_GOAL_ID = "goal-1"
    monkeypatch.setattr(f"{COMMAND_MODULE}.push_manifest", lambda: True)
    call_command("semantichub_push_manifest")


def test_command_fails_when_push_fails(settings, monkeypatch):
    settings.SEMANTICHUB_API_BASE_URL = "https://example.test"
    settings.SEMANTICHUB_AGENT_TOKEN = "tok"
    settings.SEMANTICHUB_GOAL_ID = "goal-1"
    monkeypatch.setattr(f"{COMMAND_MODULE}.push_manifest", lambda: False)
    with pytest.raises(CommandError):
        call_command("semantichub_push_manifest")
