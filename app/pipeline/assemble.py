"""Montagem final com FFmpeg: Ken Burns / clipes por cena, narração, música, legendas e acabamento."""
import subprocess
import wave

from .. import config

FPS = config.FPS

GRADES = {
    "sepia_warm": "colorbalance=rs=.08:gs=.03:bs=-.08,eq=saturation=0.85",
    "teal_amber": "colorbalance=rs=.06:bs=-.04:rh=.05:bh=-.05,eq=contrast=1.06",
    "high_contrast": "eq=contrast=1.12:saturation=1.1",
    "muted_earth": "eq=saturation=0.8:contrast=1.04",
}


class FFmpegError(RuntimeError):
    pass


def run(cmd: list[str], cwd: str | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise FFmpegError(f"{' '.join(cmd[:4])}...: {r.stderr[-1500:]}")


def _fades(frames: int, fade: float) -> str:
    if fade <= 0 or frames < FPS:
        return ""
    dur = frames / FPS
    return f",fade=t=in:st=0:d={fade},fade=t=out:st={dur - fade:.3f}:d={fade}"


def ken_burns_segment(image: str, seconds: float, out: str, variant: int = 0, fade: float = 0.3, frames: int | None = None) -> None:
    """Imagem estática com zoom/pan lento. `variant`: 0 aproxima, 1 afasta, 2 desliza."""
    W, H = config.VIDEO_W, config.VIDEO_H
    n = frames or max(1, round(seconds * FPS))
    inc = 0.25 / n
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    zoom = {
        0: f"z='min(1+{inc:.6f}*on,1.25)':{center}",
        1: f"z='max(1.25-{inc:.6f}*on,1.0)':{center}",
        2: f"z='1.15':x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)'",
    }[variant % 3]
    vf = (
        f"scale={2 * W}:{2 * H}:force_original_aspect_ratio=increase,crop={2 * W}:{2 * H},"
        f"zoompan={zoom}:d={n}:s={W}x{H}:fps={FPS}{_fades(n, fade)},format=yuv420p"
    )
    run(["ffmpeg", "-y", "-i", image, "-vf", vf, "-frames:v", str(n), "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", out])


def _clip_frames(clip: str) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", clip], capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def clip_segment(clip: str, frames: int, out: str, fade: float = 0.3) -> None:
    """Usa o clipe animado (LTX/Wan, ~4 s) no início da cena. Se a cena for mais longa, em vez de repetir o clipe
    (loop visível), o movimento se acomoda num zoom lento a partir do último quadro, sem emenda."""
    W, H = config.VIDEO_W, config.VIDEO_H
    n_clip = _clip_frames(clip)
    play = min(frames, n_clip) if n_clip else frames
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}{_fades(play, fade)},format=yuv420p"
    head = out if play >= frames else out + ".head.mp4"
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", clip, "-vf", vf, "-frames:v", str(play), "-r", str(FPS),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", head])
    if play >= frames:
        return
    last = out + ".last.png"
    run(["ffmpeg", "-y", "-sseof", "-0.2", "-i", head, "-update", "1", "-frames:v", "1", last])
    tail = out + ".tail.mp4"
    ken_burns_segment(last, 0, tail, variant=0, fade=0, frames=frames - play)
    listing = out + ".txt"
    with open(listing, "w") as f:
        f.write(f"file '{head}'\nfile '{tail}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out])


def join_narration(wavs: list[str], durations: list[float], out: str) -> None:
    """Concatena os WAVs das cenas; cada cena é preenchida com silêncio até a sua duração total."""
    with wave.open(wavs[0], "rb") as first:
        params = first.getparams()
    with wave.open(out, "wb") as o:
        o.setparams(params)
        for path, total in zip(wavs, durations):
            with wave.open(path, "rb") as w:
                data = w.readframes(w.getnframes())
                got = w.getnframes() / w.getframerate()
            o.writeframes(data)
            pad_frames = max(0, int(round((total - got) * params.framerate)))
            o.writeframes(b"\x00" * pad_frames * params.sampwidth * params.nchannels)


def finishing_filters(profile: dict) -> str:
    f = profile.get("finishing", {})
    parts = []
    if f.get("grade") in GRADES:
        parts.append(GRADES[f["grade"]])
    if f.get("vignette"):
        parts.append(f"vignette=angle=PI*{0.12 + 0.2 * float(f['vignette']):.3f}")
    if f.get("grain"):
        # grão é ruído: o codec não o comprime, então mantemos sutil (0.3 -> força 3)
        parts.append(f"noise=alls={max(1, round(float(f['grain']) * 10))}:allf=t")
    return ",".join(parts)


XFADES = {"crossfade": "fade", "fade_black": "fadeblack", "dissolve": "dissolve"}  # nome na interface -> filtro xfade
TRANSITION_PROFILE_ALIAS = {"glow_dissolve": "dissolve"}  # nomes antigos usados nos perfis


def transition_kind(option: str | None, profile: dict) -> str:
    """Resolve 'profile' (herda do perfil) para: cut | crossfade | fade_black | dissolve."""
    if not option or option == "profile":
        option = profile.get("finishing", {}).get("transition", "crossfade")
        option = TRANSITION_PROFILE_ALIAS.get(option, option)
    return option if option in ("cut", *XFADES) else "crossfade"


def join_cut(segments: list[str], out: str) -> None:
    """Corte seco: concatena sem reencodar."""
    listing = out + ".txt"
    with open(listing, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segments)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out])


def _xfade_group(files: list[str], bodies: list[int], tail: int, kind: str, out: str) -> None:
    """Encadeia `files` com xfade. Cada arquivo tem `bodies[i]` quadros visíveis + `tail` quadros de sobreposição
    (exceto o último arquivo do vídeo todo, que não tem cauda). A saída dura soma(bodies) (+tail se o último tinha cauda)."""
    if len(files) == 1:
        run(["ffmpeg", "-y", "-i", files[0], "-c", "copy", out])
        return
    cmd = ["ffmpeg", "-y"]
    for f in files:
        cmd += ["-i", f]
    prep = ";".join(f"[{i}:v]settb=AVTB,setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}]" for i in range(len(files)))
    chain, cur, offset = [], "v0", bodies[0]
    for i in range(1, len(files)):
        chain.append(f"[{cur}][v{i}]xfade=transition={kind}:duration={tail / FPS:.4f}:offset={offset / FPS:.4f}[x{i}]")
        cur, offset = f"x{i}", offset + bodies[i]
    cmd += ["-filter_complex", prep + ";" + ";".join(chain), "-map", f"[{cur}]", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-an", out]
    run(cmd)


def crossfade_join(files: list[str], bodies: list[int], tail: int, kind: str, out: str, group: int = 10) -> None:
    """Crossfade real entre cenas. Cada cena (menos a última) deve ter sido gerada com `tail` quadros a mais.

    Para vídeos longos (100+ cenas) faz em dois níveis, `group` cenas por vez, para não abrir
    centenas de entradas no mesmo comando do FFmpeg.
    """
    n = len(files)
    if n <= group:
        return _xfade_group(files, bodies, tail, kind, out)
    group_files, group_bodies = [], []
    for k, a in enumerate(range(0, n, group)):
        b = min(n, a + group)
        tmp = f"{out}.g{k}.mp4"
        _xfade_group(files[a:b], bodies[a:b], tail, kind, tmp)
        group_files.append(tmp)
        group_bodies.append(sum(bodies[a:b]))
    _xfade_group(group_files, group_bodies, tail, kind, out)


# volume final padronizado para o YouTube (~ -16 LUFS); a narração do Kokoro sai baixa (~ -27 dB de média)
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def audio_graph(music: dict | None, total_seconds: float) -> tuple[list[str], str]:
    """Entradas extras e filtro de áudio. Narração = entrada 1; música (opcional) = entrada 2.

    Com `duck`, a música abaixa sozinha quando há fala (sidechaincompress, a narração comanda o compressor)."""
    if not music:
        return [], "[1:a]anull[a]"
    vol = max(0.0, min(1.0, float(music.get("volume", 0.25))))
    fade_out = max(0.0, total_seconds - 3.0)
    mus = f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={vol:.3f},afade=t=in:d=2,afade=t=out:st={fade_out:.2f}:d=3[m]"
    nar = "[1:a]aformat=sample_rates=44100:channel_layouts=stereo"
    if music.get("duck", True):
        fc = (f"{nar},asplit=2[nar][sc];{mus};"
              "[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=600:makeup=1[duck];"
              "[nar][duck]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        fc = f"{nar}[nar];{mus};[nar][m]amix=inputs=2:duration=first:normalize=0[a]"
    return ["-stream_loop", "-1", "-i", music["path"]], fc


def final_render(project_dir: str, raw_video: str, narration: str, ass: str, profile: dict, out: str,
                 total_seconds: float, music: dict | None = None) -> None:
    fades = f"fade=t=in:st=0:d=0.6,fade=t=out:st={max(0.0, total_seconds - 1.2):.2f}:d=1.2"
    vchain = ",".join(x for x in (finishing_filters(profile), f"subtitles={ass}", fades) if x)
    extra_in, afilter = audio_graph(music, total_seconds)
    # [0:v] só passa pela cadeia de vídeo; o áudio vem do grafo acima
    fc = f"[0:v]{vchain}[v];{afilter};[a]{LOUDNORM}[aout]"
    # teto de bitrate proporcional à resolução (1080p@24 ≈ 4,5 Mbps ≈ 500 MB em 15 min)
    maxrate = max(1500, int(config.VIDEO_W * config.VIDEO_H * FPS * 0.09 / 1000))
    cmd = ["ffmpeg", "-y", "-i", raw_video, "-i", narration, *extra_in, "-filter_complex", fc, "-map", "[v]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", f"{maxrate}k", "-bufsize", f"{2 * maxrate}k",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    run(cmd, cwd=project_dir)


def short_render(project_dir: str, raw_video: str, narration: str, ass: str, profile: dict, out: str, t0: float, seconds: float,
                 layout: str = "blur", music: dict | None = None) -> None:
    """Corta [t0, t0+seconds] do vídeo sem legendas e monta um Short 1080x1920 com narração, música opcional e legendas verticais."""
    if layout == "crop":
        base = "[0:v]crop=ih*9/16:ih,scale=1080:1920,setsar=1[v0]"
    else:  # imagem inteira no meio, sobre ela mesma desfocada e escurecida
        base = ("[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:4,eq=brightness=-0.10[bg];"
                "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2-120,setsar=1[v0]")
    fades = f"fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.0, seconds - 0.6):.2f}:d=0.6"
    chain = ",".join(x for x in (finishing_filters(profile), f"subtitles={ass}", fades) if x)
    extra_in, afilter = audio_graph(music, seconds)
    fc = f"{base};[v0]{chain}[v];{afilter};[a]{LOUDNORM}[aout]"
    cmd = ["ffmpeg", "-y", "-ss", f"{t0:.3f}", "-t", f"{seconds:.3f}", "-i", raw_video, "-ss", f"{t0:.3f}", "-t", f"{seconds:.3f}", "-i", narration,
           *extra_in, "-filter_complex", fc, "-map", "[v]", "-map", "[aout]", "-t", f"{seconds:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "6000k", "-bufsize", "12000k", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    run(cmd, cwd=project_dir)


def poster_frame(video: str, out: str, at: float = 1.5) -> None:
    run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", video, "-frames:v", "1", "-q:v", "4", out])
