"""Local OCR observations with source bounding boxes; no UI actions."""
import asyncio
from pathlib import Path

from .errors import ReviewRequired
from .state import write_json


async def recognize(path):
    from winrt.windows.storage import StorageFile, FileAccessMode
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    engine = OcrEngine.try_create_from_language(Language("en-US"))
    if engine is None:
        raise ReviewRequired("Windows English OCR language pack unavailable", stage="OCR")
    file = await StorageFile.get_file_from_path_async(str(Path(path).resolve()))
    stream = await file.open_async(FileAccessMode.READ)
    try:
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        if max(bitmap.pixel_width, bitmap.pixel_height) > OcrEngine.max_image_dimension:
            raise ReviewRequired("Image exceeds Windows OCR dimensions", stage="OCR")
        result = await engine.recognize_async(bitmap)
        lines = []
        for line in result.lines:
            words = []
            for word in line.words:
                r = word.bounding_rect
                words.append(dict(text=word.text, x=r.x, y=r.y, width=r.width, height=r.height))
            lines.append({"text": line.text, "words": words})
        return {"text": result.text, "lines": lines, "width": bitmap.pixel_width, "height": bitmap.pixel_height}
    finally:
        stream.close()


def capture_ocr(path, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(recognize(path))
    write_json(directory / "ocr.json", result)
    (directory / "ocr.txt").write_text(result["text"], encoding="utf-8")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    capture_ocr(args.image, args.out)
    print(args.out / "ocr.json")
