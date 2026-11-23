"""Cliente do ComfyUI: imagens (FLUX) e clipes (LTX / Wan 2.2). Workflows validados na andes."""
import json
import time
import urllib.parse
import urllib.request


# Contra o que mais estraga animações de imagem: rosto e corpo que derretem, movimento brusco, clima assustador. Sem "static": ele manda o
# modelo mexer MAIS, e mexer mais é o que deforma.
NEGATIVE_MOTION = "worst quality, blurry, jittery, flickering, distorted face, deformed face, melting, morphing, warping, twisted body, extra limbs, extra fingers, bad anatomy, scary, creepy, horror, sudden movement, fast motion, glitch, watermark, text"


class ComfyError(RuntimeError):
    pass


class Comfy:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    # ------------------------------------------------------------ HTTP
    def _json(self, path: str, data: dict | None = None, timeout: int = 60):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        return json.loads(body) if body else {}

    def run(self, workflow: dict, timeout: int = 3600, should_stop=None) -> dict:
        """Executa o workflow. Se `should_stop()` virar True, interrompe no ComfyUI e levanta Cancelled."""
        from ... import cancel

        pid = self._json("/prompt", {"prompt": workflow})["prompt_id"]
        t0 = time.time()
        while time.time() - t0 < timeout:
            if should_stop and should_stop():
                self.interrupt()
                raise cancel.Cancelled("cancelado pelo usuário")
            hist = self._json(f"/history/{pid}")
            if pid in hist:
                st = hist[pid]["status"]
                if st.get("status_str") != "success":
                    raise ComfyError(json.dumps(st)[:1200])
                return hist[pid]["outputs"]
            time.sleep(1)
        raise ComfyError("tempo esgotado esperando o ComfyUI")

    def fetch(self, info: dict) -> bytes:
        q = urllib.parse.urlencode({"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info.get("type", "output")})
        with urllib.request.urlopen(f"{self.base}/view?{q}", timeout=120) as r:
            return r.read()

    def upload(self, path: str, name: str) -> str:
        boundary = "----mcboundary"
        with open(path, "rb") as f:
            payload = f.read()
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            "Content-Type: image/png\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + "/upload/image", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["name"]

    def interrupt(self) -> None:
        try:
            self._json("/interrupt", {}, timeout=15)
        except Exception:
            pass

    def free(self) -> None:
        try:
            self._json("/free", {"unload_models": True, "free_memory": True}, timeout=30)
        except Exception:  # descarregar é "melhor esforço"
            pass

    # ------------------------------------------------------- workflows
    @staticmethod
    def flux_workflow(prompt: str, profile: dict, seed: int, prefix: str) -> dict:
        p = profile.get("params", {})
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": f"{profile.get('base_model', 'flux1-schnell-fp8')}.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
            "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": p.get("width", 1344), "height": p.get("height", 768), "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": seed,
                "steps": p.get("steps", 4), "cfg": p.get("cfg", 1.0), "sampler_name": p.get("sampler", "euler"),
                "scheduler": p.get("scheduler", "simple"), "denoise": 1.0}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefix}},
        }

    @staticmethod
    def ltx_workflow(image: str, prompt: str, w: int, h: int, frames: int, prefix: str, seed: int = 7) -> dict:
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ltxv-2b-0.9.6-dev-04-25.safetensors"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp8_e4m3fn.safetensors", "type": "ltxv"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE_MOTION, "clip": ["2", 0]}},
            "5": {"class_type": "LoadImage", "inputs": {"image": image}},
            "6": {"class_type": "ImageScale", "inputs": {"image": ["5", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "center"}},
            "7": {"class_type": "LTXVImgToVideo", "inputs": {"positive": ["3", 0], "negative": ["4", 0], "vae": ["1", 2], "image": ["6", 0], "width": w, "height": h, "length": frames, "batch_size": 1, "strength": 1.0}},
            "8": {"class_type": "LTXVConditioning", "inputs": {"positive": ["7", 0], "negative": ["7", 1], "frame_rate": 24.0}},
            "9": {"class_type": "LTXVScheduler", "inputs": {"steps": 30, "max_shift": 2.05, "base_shift": 0.95, "stretch": True, "terminal": 0.1, "latent": ["7", 2]}},
            "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "11": {"class_type": "SamplerCustom", "inputs": {"model": ["1", 0], "add_noise": True, "noise_seed": seed, "cfg": 3.0, "positive": ["8", 0], "negative": ["8", 1], "sampler": ["10", 0], "sigmas": ["9", 0], "latent_image": ["7", 2]}},
            "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
            "13": {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "fps": 24.0}},
            "14": {"class_type": "SaveVideo", "inputs": {"video": ["13", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}},
        }

    @staticmethod
    def wan_workflow(image: str, prompt: str, w: int, h: int, frames: int, prefix: str, seed: int = 7) -> dict:
        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE_MOTION + ", subtitles", "clip": ["2", 0]}},
            "6": {"class_type": "LoadImage", "inputs": {"image": image}},
            "7": {"class_type": "ImageScale", "inputs": {"image": ["6", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "center"}},
            "8": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": w, "height": h, "length": frames, "batch_size": 1, "start_image": ["7", 0]}},
            "9": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
            "10": {"class_type": "KSampler", "inputs": {"model": ["9", 0], "seed": seed, "steps": 20, "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple", "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["8", 0], "denoise": 1.0}},
            "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
            "12": {"class_type": "CreateVideo", "inputs": {"images": ["11", 0], "fps": 24.0}},
            "13": {"class_type": "SaveVideo", "inputs": {"video": ["12", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}},
        }
