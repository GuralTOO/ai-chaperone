"""Utilities for video frame sampling."""
import base64
from io import BytesIO
from typing import Any

import av
import numpy as np
from PIL import Image


def pil_to_base64(pil_image: Image.Image) -> str:
    """Convert PIL image to b64."""
    buffer = BytesIO()
    pil_image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def sample_video_frames(video_path: str,
                        fps: int= 2,
                        max_frames: int = 10,
                        *,
                        convert_b64: bool = True) -> list[Any]:
    """Sample frames from video that have the biggest visual changes.

    Args:
        video_path: Path to video file
        fps: Target sampling rate (frames per second)
        max_frames: Maximum number of frames to return
        convert_b64: To return in base64 format or not

    Returns:
        List of PIL Images of the most visually different frames

    """
    container = av.open(video_path)
    video_stream = container.streams.video[0]

    frame_interval = 1.0 / fps

    frames = []
    differences = []
    prev_frame = None
    next_sample_time = 0.0

    try:
        for packet in container.demux(video_stream):
            for frame in packet.decode():

                if frame.pts is None or video_stream.time_base is None:
                    continue

                current_time = float(frame.pts * video_stream.time_base)

                if current_time >= next_sample_time:
                    img = frame.to_image().convert("L")
                    img.thumbnail((512, 288))
                    frame_array = np.array(img)

                    if prev_frame is not None:
                        diff = np.sum(np.abs(prev_frame.astype(np.float32) - frame_array.astype(np.float32)))
                        differences.append((len(frames), diff, img))

                    frames.append(frame_array)
                    prev_frame = frame_array
                    next_sample_time += frame_interval

    finally:
        container.close()

    if not differences:
        return []

    differences.sort(key=lambda x: x[1], reverse=True)
    top_frames = [img for _, _, img in differences[:max_frames]]
    if convert_b64:
        return [pil_to_base64(frame) for frame in top_frames]
    return top_frames
