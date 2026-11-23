"""Miniatura do YouTube: 1280x720, até 2 MB. Imagem gerada pelo FLUX + título por cima (Pillow)."""
import copy
import pathlib

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1280, 720
MAX_BYTES = 2_000_000
GOLD = (255, 200, 61)
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]
PROMPT_SUFFIX = "wide 16:9 composition, strong focal subject, empty space on the left side, no text, no letters"


def _font(size: int):
    for path in FONTS:
        if pathlib.Path(path).is_file():
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw, words: list[str], font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if cur and draw.textlength(cand, font=font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    return lines + ([cur] if cur else [])


def compose(base_path: str, text: str, out_path: str) -> None:
    """Corta a imagem em 16:9, escurece o lado esquerdo (legibilidade) e escreve o texto grande, com contorno."""
    img = ImageOps.fit(Image.open(base_path).convert("RGB"), (W, H), method=Image.LANCZOS)
    ramp = Image.new("L", (W, 1))
    for x in range(W):
        ramp.putpixel((x, 0), int(190 * max(0.0, 1 - x / (W * 0.62)) ** 1.4))
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, ramp.resize((W, H)))

    words = text.upper().split()
    if words:
        draw = ImageDraw.Draw(img)
        max_w, max_h = int(W * 0.56), int(H * 0.72)
        for size in range(170, 47, -6):
            font = _font(size)
            lines = _wrap(draw, words, font, max_w)
            if len(lines) <= 3 and all(draw.textlength(l, font=font) <= max_w for l in lines) and len(lines) * size * 1.08 <= max_h:
                break
        line_h = int(size * 1.08)
        y = (H - line_h * len(lines)) // 2
        stroke = max(4, size // 9)
        for i, line in enumerate(lines):
            color = GOLD if len(lines) > 1 and i == len(lines) - 1 else (255, 255, 255)  # a última linha ganha destaque
            draw.text((64, y + i * line_h), line, font=font, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0))

    for quality in (90, 84, 78, 70, 60):  # o YouTube aceita até 2 MB
        img.save(out_path, "JPEG", quality=quality, optimize=True)
        if pathlib.Path(out_path).stat().st_size <= MAX_BYTES:
            break


def generate(project: dict, profile: dict, backend, out_dir: pathlib.Path, progress, count: int = 3) -> dict:
    """Gera `count` variantes (imagem base + miniatura com texto). Devolve o estado para guardar no projeto."""
    yt = project["meta"].get("youtube") or {}
    text = yt.get("thumb_text") or yt.get("title") or project["title"]
    items = project["scenes"]
    subject = yt.get("thumb_prompt") or (items[0]["visual_prompt"] if items and items[0]["visual_prompt"] else project["title"])
    prof = copy.deepcopy(profile)
    prof["params"] = {**prof.get("params", {}), "width": W, "height": H}
    out_dir.mkdir(parents=True, exist_ok=True)
    seed0 = sum(map(ord, project["id"])) * 97
    variants = []
    init, st = getattr(progress, "init_stages", None), getattr(progress, "set_stage", None)
    if init:
        init([("thumb", "Miniaturas", count)])
    for i in range(1, count + 1):
        if st:
            st("thumb", i - 1)
        progress((i - 1) / count, f"gerando a miniatura {i} de {count}")
        base = out_dir / f"base_{i}.png"
        backend.image(f"{subject}. {profile['style_prompt']}. {PROMPT_SUFFIX}", prof, seed0 + i * 1013, str(base), (W, H))
        jpg = out_dir / f"thumb_{i}.jpg"
        compose(str(base), text, str(jpg))
        variants.append({"i": i, "text": text, "base": f"thumbs_yt/{base.name}", "file": f"thumbs_yt/{jpg.name}"})
        if st:
            st("thumb", i)
    backend.unload("image")
    prev = project["meta"].get("thumbnail") or {}
    return {"variants": variants, "selected": 1, "ver": prev.get("ver", 0) + 1}
