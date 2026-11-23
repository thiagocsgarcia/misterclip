"""Crossfade real entre cenas e música com redução de volume (ducking): testes com FFmpeg de verdade."""
import math
import re
import struct
import subprocess
import wave

import pytest

from app.pipeline import assemble

FPS = assemble.FPS


def ff(*args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r


def video_seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out)


def make_segment(path, frames, color):
    ff("-f", "lavfi", "-i", f"color=c={color}:s=160x90:r={FPS}", "-frames:v", str(frames), "-pix_fmt", "yuv420p", str(path))


def test_transition_kind_resolution():
    prof = {"finishing": {"transition": "glow_dissolve"}}
    assert assemble.transition_kind(None, prof) == "dissolve"
    assert assemble.transition_kind("profile", {"finishing": {"transition": "fade_black"}}) == "fade_black"
    assert assemble.transition_kind("cut", prof) == "cut"
    assert assemble.transition_kind("bobagem", {}) == "crossfade"


@pytest.mark.parametrize("n_scenes", [4, 25])  # 25 > grupo de 10: exercita o modo em dois níveis
def test_crossfade_total_duration_equals_sum_of_scenes(tmp_path, n_scenes):
    body, tail = 30, 6
    colors = ["red", "green", "blue", "yellow", "white"]
    files, bodies = [], []
    for i in range(n_scenes):
        f = tmp_path / f"s{i}.mp4"
        make_segment(f, body + (tail if i < n_scenes - 1 else 0), colors[i % len(colors)])
        files.append(str(f))
        bodies.append(body)
    out = tmp_path / "joined.mp4"
    assemble.crossfade_join(files, bodies, tail, "fade", str(out))
    expected = n_scenes * body / FPS
    assert abs(video_seconds(out) - expected) < 0.2, (video_seconds(out), expected)  # sem deriva acumulada


def test_crossfade_actually_blends_colors(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    make_segment(a, 30 + 12, "red")
    make_segment(b, 30, "blue")
    out = tmp_path / "x.mp4"
    assemble.crossfade_join([str(a), str(b)], [30, 30], 12, "fade", str(out))
    # no meio da transição (t = 30/24 + 6/24 s) o pixel não é vermelho puro nem azul puro
    mid = 30 / FPS + 6 / FPS
    ff("-ss", f"{mid:.3f}", "-i", str(out), "-frames:v", "1", "-vf", "scale=1:1,format=rgb24", "-f", "rawvideo", str(tmp_path / "px.bin"))
    r, g, bl = (tmp_path / "px.bin").read_bytes()[:3]
    assert r > 60 and bl > 60, (r, g, bl)


def write_wav(path, segments, rate=44100):
    """segments = [(segundos, frequência, amplitude)]; frequência 0 = silêncio."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for sec, freq, amp in segments:
            n = int(sec * rate)
            w.writeframes(b"".join(struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * freq * i / rate)) if freq else 0) for i in range(n)))


def band_level(wav, start, dur, freq):
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(start), "-t", str(dur), "-i", str(wav), "-af",
                        f"bandpass=f={freq}:width_type=h:width=80,volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    return float(re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr).group(1))


def mix(tmp_path, duck):
    nar, mus, out = tmp_path / "nar.wav", tmp_path / "mus.wav", tmp_path / f"mix_{duck}.wav"
    write_wav(nar, [(2.5, 0, 0), (3.0, 220, 0.6), (3.0, 0, 0)])  # fala (220 Hz) entre 2,5 s e 5,5 s
    write_wav(mus, [(8.0, 440, 0.5)])                              # música constante (440 Hz)
    extra, fc = assemble.audio_graph({"path": str(mus), "volume": 0.5, "duck": duck}, total_seconds=60)
    ff("-f", "lavfi", "-i", "color=c=black:s=64x64:d=8", "-i", str(nar), *extra, "-filter_complex", fc,
       "-map", "[a]", "-t", "8", str(out))
    return out


def test_ducking_lowers_music_while_narration_speaks(tmp_path):
    out = mix(tmp_path, duck=True)
    speaking = band_level(out, 3.2, 2.0, 440)   # música durante a fala
    silent = band_level(out, 6.6, 1.5, 440)     # música depois da fala (já recuperou)
    assert silent - speaking > 6, (speaking, silent)


def test_without_ducking_music_level_is_constant(tmp_path):
    out = mix(tmp_path, duck=False)
    assert abs(band_level(out, 3.2, 2.0, 440) - band_level(out, 6.6, 1.5, 440)) < 2


def test_no_music_graph_is_passthrough():
    extra, fc = assemble.audio_graph(None, 10)
    assert extra == [] and fc == "[1:a]anull[a]"


def test_loudnorm_brings_quiet_narration_to_target(tmp_path):
    """A narração do Kokoro é baixa (~ -27 dB de média); o estágio final a leva para perto de -16 LUFS."""
    quiet = tmp_path / "quiet.wav"
    ff("-f", "lavfi", "-i", "anoisesrc=d=20:c=pink:r=44100:a=0.02", "-af", "lowpass=f=3000", str(quiet))
    out = tmp_path / "norm.wav"
    ff("-i", str(quiet), "-af", assemble.LOUDNORM, str(out))
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(out), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])
    assert -18.5 <= lufs <= -13.5, lufs
