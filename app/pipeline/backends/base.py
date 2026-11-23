"""Contrato dos backends. O pipeline só conhece esta interface."""
from typing import Protocol


class Backend(Protocol):
    name: str

    def visual_prompt(self, scene_text: str, system: str | None = None, extra: str = "") -> str:
        """Descrição visual concreta (em inglês) para o gerador de imagens."""

    def llm_text(self, system: str, user: str, max_tokens: int = 1200) -> str:
        """Texto livre do LLM (roteiros)."""

    def llm_json(self, system: str, user: str) -> dict:
        """Pede ao LLM uma resposta em JSON (objeto) e a devolve já convertida."""

    def tts(self, text: str, voice: str, speed: float, out_wav: str) -> float:
        """Gera a narração em WAV mono 24 kHz 16 bits. Retorna a duração em segundos."""

    def align(self, wav: str, words: list[str], duration: float) -> list[list]:
        """Tempos por palavra do texto original: [[palavra, início, fim], ...]."""

    def transcribe_lyrics(self, path: str, duration: float | None = None) -> list[dict]:
        """Letra cantada: [{start, end, text}, ...] em português."""

    def image(self, prompt: str, profile: dict, seed: int, out_png: str, size: tuple[int, int]) -> None:
        """Gera uma imagem (já com o bloco de estilo do perfil dentro do prompt)."""

    def clip(self, engine: str, image: str, prompt: str, out_mp4: str, seconds: float, seed: int = 7) -> bool:
        """Anima a imagem. False = não suportado (o pipeline cai para Ken Burns)."""

    def unload(self, stage: str) -> None:
        """Descarrega da GPU o modelo da etapa (tts | align | image | clip | llm)."""
