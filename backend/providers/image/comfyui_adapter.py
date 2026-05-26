from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from infra.config import settings
from interfaces.image import ImageProvider, ImageResult, ImageStatus

logger = logging.getLogger(__name__)


class ComfyUIAdapter(ImageProvider):
    """REST client for ComfyUI's HTTP API.

    ComfyUI endpoints:
      POST /api/prompt        — submit workflow JSON → {"prompt_id": "..."}
      GET  /api/history/{id}  — generation result with output filenames
      GET  /api/view?filename=— download generated image
      POST /api/upload/image  — upload reference image for InstantID
    """

    def __init__(self, base_url: str | None = None, timeout: int = 300) -> None:
        self._base_url = (base_url or getattr(settings, "comfyui_base_url", "http://localhost:8188")).rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))
        return self._client

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self._base_url}/system_stats")
            return resp.status_code == 200
        except Exception:
            return False

    async def generate(self, workflow: dict) -> str:
        client = await self._get_client()
        payload = {"prompt": workflow}
        resp = await client.post(f"{self._base_url}/api/prompt", json=payload)
        resp.raise_for_status()
        data = resp.json()
        prompt_id = data.get("prompt_id", "")
        logger.info("comfyui job submitted: %s", prompt_id)
        return prompt_id

    async def poll(self, prompt_id: str) -> ImageResult:
        client = await self._get_client()

        # Poll for completion
        max_polls = 60
        for i in range(max_polls):
            try:
                resp = await client.get(f"{self._base_url}/api/history/{prompt_id}")
                if resp.status_code == 200:
                    history = resp.json()
                    if prompt_id in history:
                        entry = history[prompt_id]
                        outputs = entry.get("outputs", {})
                        images = []
                        filenames = []
                        for node_id, node_output in outputs.items():
                            for img in node_output.get("images", []):
                                fn = img.get("filename", "")
                                if fn:
                                    filenames.append(fn)
                                    img_resp = await client.get(
                                        f"{self._base_url}/api/view",
                                        params={"filename": fn, "subfolder": img.get("subfolder", "")},
                                    )
                                    if img_resp.status_code == 200:
                                        images.append(img_resp.content)
                        return ImageResult(
                            prompt_id=prompt_id,
                            status=ImageStatus.DONE,
                            images=images,
                            filenames=filenames,
                        )
                # Not done yet — keep polling
            except Exception as e:
                logger.warning("comfyui poll %d error: %s", i, e)

            await asyncio.sleep(2)

        return ImageResult(
            prompt_id=prompt_id,
            status=ImageStatus.FAILED,
            error="timeout waiting for generation",
        )

    async def upload_image(self, filename: str, data: bytes) -> str:
        client = await self._get_client()
        files = {"image": (filename, data, "image/png")}
        resp = await client.post(f"{self._base_url}/api/upload/image", files=files)
        resp.raise_for_status()
        result = resp.json()
        return result.get("name", filename)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class InstantIDWorkflow:
    """Builds ComfyUI workflow JSON with InstantID IP-Adapter for face consistency.

    The workflow includes:
      - Checkpoint load (SDXL or SD 1.5)
      - CLIP text encode (positive + negative prompt)
      - InstantID IP-Adapter (face embedding from reference image)
      - KSampler (steps, cfg, sampler, seed)
      - VAE decode
      - Save image output
    """

    @staticmethod
    def build_character_ref_workflow(
        prompt: str,
        negative_prompt: str,
        seed: int,
        width: int = 768,
        height: int = 1152,
        steps: int = 25,
        cfg: float = 7.5,
        sampler: str = "dpmpp_2m",
        checkpoint: str = "sd_xl_base_1.0.safetensors",
    ) -> dict:
        """Build workflow for reference portrait (NO InstantID — face is generated fresh)."""
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": seed, "steps": steps, "cfg": cfg,
                "sampler_name": sampler, "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0],
                "latent_image": ["5", 0],
            }},
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {
                "ckpt_name": checkpoint,
            }},
            "5": {"class_type": "EmptyLatentImage", "inputs": {
                "width": width, "height": height, "batch_size": 1,
            }},
            "6": {"class_type": "CLIPTextEncode", "inputs": {
                "text": prompt, "clip": ["4", 1],
            }},
            "7": {"class_type": "CLIPTextEncode", "inputs": {
                "text": negative_prompt, "clip": ["4", 1],
            }},
            "8": {"class_type": "VAEDecode", "inputs": {
                "samples": ["3", 0], "vae": ["4", 2],
            }},
            "9": {"class_type": "SaveImage", "inputs": {
                "filename_prefix": "char_ref", "images": ["8", 0],
            }},
        }
        return workflow

    @staticmethod
    def build_instantid_workflow(
        prompt: str,
        negative_prompt: str,
        face_image_filename: str,
        seed: int,
        width: int = 768,
        height: int = 1152,
        steps: int = 25,
        cfg: float = 7.5,
        sampler: str = "dpmpp_2m",
        checkpoint: str = "sd_xl_base_1.0.safetensors",
        ip_weight: float = 0.8,
    ) -> dict:
        """Build workflow with InstantID IP-Adapter for face-consistent character images.

        face_image_filename is the name returned by upload_image() — the reference
        portrait stored on the ComfyUI server.
        """
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {
                "image": face_image_filename,
            }},
            "2": {"class_type": "IPAdapterInstantID", "inputs": {
                "image": ["1", 0],
                "weight": ip_weight,
                "model": ["4", 0],
                "clip_vision": ["4", 3],  # CLIP Vision from checkpoint
            }},
            "3": {"class_type": "KSampler", "inputs": {
                "seed": seed, "steps": steps, "cfg": cfg,
                "sampler_name": sampler, "scheduler": "normal",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["6", 0], "negative": ["7", 0],
                "latent_image": ["5", 0],
            }},
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {
                "ckpt_name": checkpoint,
            }},
            "5": {"class_type": "EmptyLatentImage", "inputs": {
                "width": width, "height": height, "batch_size": 1,
            }},
            "6": {"class_type": "CLIPTextEncode", "inputs": {
                "text": prompt, "clip": ["4", 1],
            }},
            "7": {"class_type": "CLIPTextEncode", "inputs": {
                "text": negative_prompt, "clip": ["4", 1],
            }},
            "8": {"class_type": "VAEDecode", "inputs": {
                "samples": ["3", 0], "vae": ["4", 2],
            }},
            "9": {"class_type": "SaveImage", "inputs": {
                "filename_prefix": "char_instantid", "images": ["8", 0],
            }},
        }
        return workflow
