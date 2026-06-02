from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from cocode_viva.config import MAX_EXTRACTED_FILES, MAX_FILE_BYTES, MAX_ZIP_BYTES


class ArchiveError(ValueError):
    pass


def safe_extract_zip(zip_path: Path, target_dir: Path) -> list[str]:
    """Extract a zip file while preventing path traversal and oversized files."""

    if zip_path.stat().st_size > MAX_ZIP_BYTES:
        raise ArchiveError("压缩包超过 8MB，请只提交源代码、记录和报告文本。")

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    extracted: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_EXTRACTED_FILES:
            raise ArchiveError("压缩包文件数量过多，请保持作业结构精简。")

        for info in infos:
            if info.file_size > MAX_FILE_BYTES:
                raise ArchiveError(f"{info.filename} 超过单文件 512KB 限制。")

            destination = (target_dir / info.filename).resolve()
            if not str(destination).startswith(str(target_dir.resolve())):
                raise ArchiveError("压缩包包含非法路径。")

            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(destination.relative_to(target_dir).as_posix())

    return extracted

