"""FFmpeg media adapter for export and inspection."""
import shutil
import subprocess
from pathlib import Path


QUALITY = {
    "720p": (1280, 720, "4M"),
    "1080p": (1920, 1080, "8M"),
    "2k": (2560, 1440, "16M"),
    "4k": (3840, 2160, "35M"),
}


class MediaError(RuntimeError):
    pass


class FFmpegService:
    @property
    def available(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def capabilities(self) -> dict[str, object]:
        return {"available": self.available, "binary": shutil.which("ffmpeg"), "formats": ["mp4", "gif", "webm", "mov"]}

    def probe(self, source: str) -> dict[str, str]:
        if not self.available:
            raise MediaError("FFmpeg is not installed")
        result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", source], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            raise MediaError(result.stderr.strip() or "Could not inspect media")
        return {"raw": result.stdout}

    def export_h264(self, source: str, destination: str, quality: str = "1080p", fps: int = 24) -> str:
        if not self.available:
            raise MediaError("FFmpeg is not installed")
        if quality not in QUALITY:
            raise MediaError(f"Unsupported quality: {quality}")
        width, height, bitrate = QUALITY[quality]
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        command = ["ffmpeg", "-y", "-i", source, "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2", "-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", bitrate, "-movflags", "+faststart", destination]
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            raise MediaError(result.stderr[-1000:] or "FFmpeg export failed")
        return destination


media = FFmpegService()
