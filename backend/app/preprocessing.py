"""Reference preprocessing providers for ControlNet conditioning."""
from pathlib import Path


class PreprocessingError(RuntimeError):
    pass


class ReferencePreprocessor:
    def preprocess(self, source: str, mode: str, destination: str) -> str:
        if mode in {"edges", "depth", "tile"}:
            return self._pillow(source, mode, destination)
        if mode == "pose":
            return self._openpose(source, destination)
        raise PreprocessingError(f"Unsupported preprocessing mode: {mode}")

    def _pillow(self, source: str, mode: str, destination: str) -> str:
        try:
            from PIL import Image, ImageFilter
        except ImportError as error:
            raise PreprocessingError("Pillow is required for reference preprocessing") from error
        image = Image.open(source).convert("RGB")
        if mode == "depth":
            result = image.convert("L")
        elif mode == "edges":
            result = image.filter(ImageFilter.FIND_EDGES)
        else:
            result = image
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        result.save(destination, format="PNG")
        return destination

    def _openpose(self, source: str, destination: str) -> str:
        try:
            from controlnet_aux import OpenposeDetector
        except ImportError as error:
            raise PreprocessingError("controlnet-aux is required for OpenPose preprocessing") from error
        detector = OpenposeDetector.from_pretrained("lllyasviel/ControlNet")
        result = detector(source)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        result.save(destination)
        return destination


preprocessor = ReferencePreprocessor()
