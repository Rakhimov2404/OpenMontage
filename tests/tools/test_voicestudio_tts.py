"""Tests for the VoiceStudio local TTS tool. No live server: HTTP is monkeypatched."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from tools.audio.voicestudio_tts import MAX_INPUT_CHARS, VoiceStudioTTS
from tools.base_tool import ToolRuntime, ToolStatus
from tools.tool_registry import ToolRegistry

FAKE_WAV = b"RIFF" + b"\x00" * 64


class _Resp:
    def __init__(self, status_code=200, content=FAKE_WAV, text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("VOICESTUDIO_URL", raising=False)
    monkeypatch.delenv("VOICESTUDIO_API_KEY", raising=False)


@pytest.fixture
def server(monkeypatch):
    calls = {}

    def fake_get(url, headers=None, timeout=None):
        calls["get"] = (url, headers)
        return _Resp()

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["post"] = (url, json, headers)
        return calls.get("post_response", _Resp())

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr("tools.analysis.audio_probe.probe_duration", lambda p: 1.5)
    return calls


def test_identity_and_discovery():
    t = VoiceStudioTTS()
    assert (t.name, t.capability, t.provider) == ("voicestudio_tts", "tts", "voicestudio")
    assert t.runtime == ToolRuntime.LOCAL
    assert t.estimate_cost({"text": "x" * 1000}) == 0.0
    reg = ToolRegistry()
    reg.discover("tools")
    assert "voicestudio_tts" in [x.name for x in reg.get_by_capability("tts")]


def test_unavailable_when_server_down(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", boom)
    assert VoiceStudioTTS().get_status() == ToolStatus.UNAVAILABLE
    result = VoiceStudioTTS().execute({"text": "salom"})
    assert not result.success and "not reachable" in result.error


def test_generates_audio_via_openai_compatible_route(server, tmp_path, monkeypatch):
    monkeypatch.setenv("VOICESTUDIO_URL", "http://127.0.0.1:4000/")
    monkeypatch.setenv("VOICESTUDIO_API_KEY", "k")
    out = tmp_path / "a" / "n.wav"
    result = VoiceStudioTTS().execute(
        {"text": "Salom dunyo", "voice_id": "prof-1", "language": "uz", "output_path": str(out)}
    )
    assert result.success, result.error
    assert out.read_bytes() == FAKE_WAV
    url, payload, headers = server["post"]
    assert url == "http://127.0.0.1:4000/v1/audio/speech"
    assert headers == {"Authorization": "Bearer k"}
    assert payload["input"] == "Salom dunyo"
    assert payload["voice"] == "prof-1"
    assert payload["language"] == "uz"
    assert payload["model"] == "omnivoice"
    assert payload["response_format"] == "wav"
    assert "seed" not in payload
    assert result.data["audio_duration_seconds"] == 1.5
    assert result.cost_usd == 0.0


def test_http_error_is_reported(server, tmp_path):
    server["post_response"] = _Resp(status_code=409, content=b"", text="ambiguous voice")
    result = VoiceStudioTTS().execute({"text": "hi", "output_path": str(tmp_path / "x.wav")})
    assert not result.success and "409" in result.error


def test_rejects_overlong_text_without_calling_server(server):
    result = VoiceStudioTTS().execute({"text": "a" * (MAX_INPUT_CHARS + 1)})
    assert not result.success and str(MAX_INPUT_CHARS) in result.error
    assert "post" not in server
