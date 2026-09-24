"""FFmpeg helpers used by the Video → Imagem desktop app.

The module intentionally depends only on the Python standard library. FFmpeg is
resolved from the system PATH first, then from the optional imageio-ffmpeg
package (which ships a portable FFmpeg executable).
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FFmpegError(RuntimeError):
    """A media operation could not be completed by FFmpeg."""


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    duration: float | None
    fps: float | None = None


def find_ffmpeg() -> str | None:
    """Return an FFmpeg executable, preferring a system install."""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, OSError, RuntimeError):
        return None

    return bundled_ffmpeg if Path(bundled_ffmpeg).is_file() else None


def parse_timestamp(value: str) -> float:
    """Parse seconds, MM:SS, or HH:MM:SS into a non-negative number of seconds.

    A comma may be used as the decimal separator (for example ``1,25``).
    """
    text = value.strip().replace(",", ".")
    if not text:
        raise ValueError("Informe o instante do quadro.")

    parts = text.split(":")
    try:
        if len(parts) == 1:
            seconds = float(parts[0])
        elif len(parts) == 2:
            minutes = float(parts[0])
            remaining_seconds = float(parts[1])
            if minutes < 0 or not 0 <= remaining_seconds < 60:
                raise ValueError
            seconds = minutes * 60 + remaining_seconds
        elif len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            remaining_seconds = float(parts[2])
            if hours < 0 or not 0 <= minutes < 60 or not 0 <= remaining_seconds < 60:
                raise ValueError
            seconds = hours * 3600 + minutes * 60 + remaining_seconds
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(
            "Use segundos, MM:SS ou HH:MM:SS.mmm (por exemplo, 00:01:23.500)."
        ) from exc

    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("O instante deve ser um número finito e não negativo.")
    return seconds


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm, including durations longer than a day."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("O instante deve ser um número finito e não negativo.")

    total_milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def _ffmpeg_timestamp(seconds: float) -> str:
    return f"{seconds:.6f}".rstrip("0").rstrip(".") or "0"


def parse_probe_output(output: str) -> VideoInfo:
    """Extract the first video stream's dimensions and duration from FFmpeg text."""
    video_line = next(
        (line for line in output.splitlines() if re.search(r"\bVideo:\s", line)),
        None,
    )
    if video_line is None:
        raise FFmpegError(
            "Não foi encontrado um fluxo de vídeo nesse arquivo. "
            "Confira se o arquivo não está corrompido."
        )

    dimensions = re.search(r"(?<!\d)(\d{2,6})x(\d{2,6})(?!\d)", video_line)
    if dimensions is None:
        raise FFmpegError(
            "O FFmpeg encontrou o vídeo, mas não conseguiu identificar a resolução."
        )

    width, height = int(dimensions.group(1)), int(dimensions.group(2))
    if width <= 0 or height <= 0:
        raise FFmpegError("A resolução informada pelo vídeo é inválida.")

    duration_match = re.search(
        r"\bDuration:\s*(\d{1,}):(\d{2}):(\d{2}(?:\.\d+)?)", output
    )
    duration: float | None = None
    if duration_match:
        hours, minutes = int(duration_match.group(1)), int(duration_match.group(2))
        seconds = float(duration_match.group(3))
        duration = hours * 3600 + minutes * 60 + seconds

    fps_match = re.search(r"(\d+(?:\.\d+)?)\s+fps\b", video_line)
    fps = float(fps_match.group(1)) if fps_match else None
    if fps is not None and (not math.isfinite(fps) or fps <= 0):
        fps = None

    return VideoInfo(width=width, height=height, duration=duration, fps=fps)


def _require_ffmpeg(ffmpeg_path: str | None) -> str:
    executable = ffmpeg_path or find_ffmpeg()
    if not executable:
        raise FFmpegError(
            "FFmpeg não foi encontrado. Instale as dependências do projeto com "
            "‘python -m pip install -r requirements.txt’ ou instale o FFmpeg no sistema."
        )
    return executable


def _check_video_path(video_path: str | Path) -> Path:
    path = Path(video_path).expanduser()
    if not path.is_file():
        raise FFmpegError(f"O arquivo de vídeo não foi encontrado:\n{path}")
    return path


def _friendly_ffmpeg_error(stderr: str, fallback: str) -> str:
    details = stderr.strip()
    if not details:
        return fallback
    # Keep the useful end of FFmpeg's diagnostic without flooding the GUI.
    lines = [line.strip() for line in details.splitlines() if line.strip()]
    return "\n".join(lines[-5:]) if lines else fallback


def probe_video(
    video_path: str | Path,
    ffmpeg_path: str | None = None,
) -> VideoInfo:
    """Read basic video metadata without decoding the complete file."""
    path = _check_video_path(video_path)
    executable = _require_ffmpeg(ffmpeg_path)
    try:
        result = subprocess.run(
            [executable, "-hide_banner", "-i", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("A leitura das informações do vídeo excedeu o tempo limite.") from exc
    except OSError as exc:
        raise FFmpegError(f"Não foi possível iniciar o FFmpeg:\n{exc}") from exc

    output = f"{result.stdout}\n{result.stderr}"
    try:
        return parse_probe_output(output)
    except FFmpegError as exc:
        details = _friendly_ffmpeg_error(result.stderr, "")
        if details:
            raise FFmpegError(f"{exc}\n\nDetalhes do FFmpeg:\n{details}") from exc
        raise


def extract_preview(
    video_path: str | Path,
    timestamp: float,
    ffmpeg_path: str | None = None,
    max_width: int = 560,
    max_height: int = 360,
) -> bytes:
    """Extract a small PPM preview suitable for Tk's built-in PhotoImage."""
    path = _check_video_path(video_path)
    executable = _require_ffmpeg(ffmpeg_path)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("O instante deve ser um número finito e não negativo.")
    if max_width < 1 or max_height < 1:
        raise ValueError("O tamanho da pré-visualização é inválido.")

    preview_filter = (
        f"scale={max_width}:{max_height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={max_width}:{max_height}:(ow-iw)/2:(oh-ih)/2:color=0x0c111b"
    )
    command = [
        executable,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        _ffmpeg_timestamp(timestamp),
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-an",
        "-vf",
        preview_filter,
        "-f",
        "image2pipe",
        "-vcodec",
        "ppm",
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("A pré-visualização excedeu o tempo limite.") from exc
    except OSError as exc:
        raise FFmpegError(f"Não foi possível iniciar o FFmpeg:\n{exc}") from exc

    if result.returncode != 0 or not result.stdout:
        details = _friendly_ffmpeg_error(
            result.stderr.decode("utf-8", errors="replace"),
            "Nenhum quadro foi retornado pelo vídeo nesse instante.",
        )
        raise FFmpegError(f"Não foi possível pré-visualizar esse quadro.\n{details}")
    return result.stdout


def _jpeg_quality_scale(quality: int) -> int:
    """Translate the 1–100 app slider to FFmpeg's inverse 2–31 JPEG scale."""
    quality = max(1, min(100, int(quality)))
    return max(2, min(31, round(31 - (quality / 100) * 29)))


def export_frame(
    video_path: str | Path,
    output_path: str | Path,
    timestamp: float,
    image_format: str,
    quality: int = 95,
    output_width: int | None = None,
    overwrite: bool = False,
    ffmpeg_path: str | None = None,
) -> Path:
    """Export one video frame as a high-quality JPEG or WebP image."""
    source = _check_video_path(video_path)
    executable = _require_ffmpeg(ffmpeg_path)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("O instante deve ser um número finito e não negativo.")
    if not 1 <= int(quality) <= 100:
        raise ValueError("A qualidade deve estar entre 1 e 100.")
    if output_width is not None and not 16 <= int(output_width) <= 32_768:
        raise ValueError("A largura de saída deve estar entre 16 e 32.768 pixels.")

    normalized_format = image_format.strip().lower()
    if normalized_format in {"jpg", "jpeg"}:
        normalized_format = "jpeg"
        valid_suffixes = {".jpg", ".jpeg"}
    elif normalized_format == "webp":
        valid_suffixes = {".webp"}
    else:
        raise ValueError("O formato de saída deve ser JPG/JPEG ou WebP.")

    destination = Path(output_path).expanduser()
    if destination.suffix.lower() not in valid_suffixes:
        raise ValueError(
            f"A extensão do arquivo não corresponde ao formato escolhido ({normalized_format.upper()})."
        )
    if not destination.parent.is_dir():
        raise FFmpegError(f"A pasta de destino não existe:\n{destination.parent}")
    if destination.exists() and not overwrite:
        raise FFmpegError(f"O arquivo já existe:\n{destination}\nEscolha outro nome ou confirme a substituição.")

    command: list[str] = [
        executable,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
        "-ss",
        _ffmpeg_timestamp(timestamp),
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
    ]

    if output_width is not None:
        command.extend(["-vf", f"scale={int(output_width)}:-1:flags=lanczos"])

    if normalized_format == "jpeg":
        command.extend(
            [
                "-c:v",
                "mjpeg",
                "-q:v",
                str(_jpeg_quality_scale(int(quality))),
                "-pix_fmt",
                "yuvj444p",
            ]
        )
    else:
        command.extend(
            [
                "-c:v",
                "libwebp",
                "-quality",
                str(int(quality)),
                "-compression_level",
                "6",
                "-preset",
                "photo",
            ]
        )
    command.append(str(destination))

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("A exportação excedeu o tempo limite de cinco minutos.") from exc
    except OSError as exc:
        raise FFmpegError(f"Não foi possível iniciar o FFmpeg:\n{exc}") from exc

    if result.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        details = _friendly_ffmpeg_error(
            result.stderr,
            "O FFmpeg não criou uma imagem válida. Confira o arquivo e o formato escolhido.",
        )
        raise FFmpegError(f"Falha ao exportar o quadro.\n{details}")

    return destination
