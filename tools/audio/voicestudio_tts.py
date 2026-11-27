"""VoiceStudio local text-to-speech provider tool.

VoiceStudio (https://github.com/debpalash/VoiceStudio) is a free, fully local
voice-cloning and TTS app. Its backend exposes an OpenAI-compatible
``POST /v1/audio/speech`` route, which this tool calls over HTTP. Nothing
leaves the machine and there is no per-character cost.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

DEFAULT_URL = "http://localhost:3900"
# VoiceStudio's SpeechRequest caps `input` at 4096 characters.
MAX_INPUT_CHARS = 4096
_FORMATS = ["mp3", "opus", "aac", "flac", "wav", "pcm"]


class VoiceStudioTTS(BaseTool):
    name = "voicestudio_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "voicestudio"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.LOCAL

    dependencies = []
    install_instructions = (
        "Install and start VoiceStudio (free, local):\n"
        "  https://github.com/debpalash/VoiceStudio/releases/latest\n"
        "Open the app once so its backend runs (default http://localhost:3900).\n"
        "Optional .env overrides:\n"
        "  VOICESTUDIO_URL=http://localhost:3900\n"
        "  VOICESTUDIO_API_KEY=...   # only if VoiceStudio has OMNIVOICE_API_KEY set"
    )
    fallback = "piper_tts"
    fallback_tools = ["piper_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "voice_cloning",
        "offline_generation",
    ]
    supports = {
        "voice_cloning": True,
        "multilingual": True,
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "free local narration with cloned voices",
        "languages poorly covered by cloud TTS (e.g. Uzbek)",
        "privacy-sensitive local-only workflows",
    ]
    not_good_for = [
        "machines without a VoiceStudio install",
        "CPU-only hosts on long scripts (slow)",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "maxLength": MAX_INPUT_CHARS},
            "voice": {
                "type": "string",
                "default": "default",
                "description": (
                    "VoiceStudio voice profile ID or name (see GET /v1/audio/voices), "
                    "or 'default'."
                ),
            },
            "voice_id": {
                "type": "string",
                "description": "Alias for voice (tts_selector passes voice_id).",
            },
            "model": {
                "type": "string",
                "default": "omnivoice",
                "description": "VoiceStudio engine id, e.g. omnivoice, voxcpm2, cosyvoice.",
            },
            "language": {
                "type": "string",
                "description": "ISO 639-1 language code, e.g. uz, ru, en.",
            },
            "instructions": {
                "type": "string",
                "description": "Optional style/delivery instruction for the engine.",
            },
            "response_format": {
                "type": "string",
                "default": "wav",
                "enum": _FORMATS,
            },
            "speed": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.25,
                "maximum": 4.0,
            },
            "seed": {"type": "integer", "description": "Fix for reproducible takes."},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=512, vram_mb=0, disk_mb=50, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["timeout"])
    idempotency_key_fields = [
        "text", "voice", "voice_id", "model", "language", "instructions",
        "response_format", "speed", "seed",
    ]
    side_effects = ["writes audio file to output_path", "calls local VoiceStudio server"]
    user_visible_verification = ["Listen to generated audio for intelligibility and voice match"]

    @staticmethod
    def _base_url() -> str:
        return (os.environ.get("VOICESTUDIO_URL") or DEFAULT_URL).strip().rstrip("/")

    @staticmethod
    def _headers() -> dict[str, str]:
        key = (os.environ.get("VOICESTUDIO_API_KEY") or "").strip()
        return {"Authorization": f"Bearer {key}"} if key else {}

    def get_status(self) -> ToolStatus:
        import requests

        try:
            resp = requests.get(
                f"{self._base_url()}/v1/models", headers=self._headers(), timeout=3
            )
        except Exception:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE if resp.status_code == 200 else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        text = inputs.get("text") or ""
        if not text.strip():
            return ToolResult(success=False, error="VoiceStudio TTS needs non-empty text.")
        if len(text) > MAX_INPUT_CHARS:
            return ToolResult(
                success=False,
                error=(
                    f"Text is {len(text)} characters; VoiceStudio accepts at most "
                    f"{MAX_INPUT_CHARS} per request. Split narration per scene/segment."
                ),
            )
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(
                success=False,
                error=f"VoiceStudio not reachable at {self._base_url()}. " + self.install_instructions,
            )

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=f"VoiceStudio TTS failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        result.cost_usd = 0.0
        return result

    def _build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": inputs.get("model") or "omnivoice",
            "input": inputs["text"],
            "voice": inputs.get("voice") or inputs.get("voice_id") or "default",
            "response_format": inputs.get("response_format") or "wav",
            "speed": inputs.get("speed", 1.0),
        }
        for field in ("language", "instructions", "seed"):
            if inputs.get(field) is not None:
                payload[field] = inputs[field]
        return payload

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        import requests

        from tools.analysis.audio_probe import probe_duration

        payload = self._build_payload(inputs)
        fmt = payload["response_format"]
        output_path = Path(inputs.get("output_path") or f"voicestudio_tts.{fmt}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Local models can take minutes on CPU, so the read timeout is generous.
        resp = requests.post(
            f"{self._base_url()}/v1/audio/speech",
            json=payload,
            headers=self._headers(),
            timeout=(5, 900),
        )
        if resp.status_code != 200:
            return ToolResult(
                success=False,
                error=f"VoiceStudio returned HTTP {resp.status_code}: {resp.text[:500]}",
            )
        if not resp.content:
            return ToolResult(success=False, error="VoiceStudio returned empty audio.")

        output_path.write_bytes(resp.content)
        audio_duration = probe_duration(output_path)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": payload["model"],
                "voice": payload["voice"],
                "language": payload.get("language"),
                "format": fmt,
                "speed": payload["speed"],
                "text_length": len(payload["input"]),
                "audio_duration_seconds": round(audio_duration, 2) if audio_duration else None,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
            model=payload["model"],
        )
