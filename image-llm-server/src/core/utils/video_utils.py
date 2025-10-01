import av
import numpy as np
from PIL import Image
import base64
from io import BytesIO

def pil_to_base64(pil_image):
    buffer = BytesIO()
    pil_image.save(buffer, format='JPEG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def sample_video_frames(video_path, 
                        fps=2, 
                        max_frames=10, 
                        convert_b64=True):
    """
    Sample frames from video that have the biggest visual changes.
    
    Args:
        video_path: Path to video file
        fps: Target sampling rate (frames per second)
        max_frames: Maximum number of frames to return
    
    Returns:
        List of PIL Images of the most visually different frames
    """
    container = av.open(video_path)
    video_stream = container.streams.video[0]
    
    original_fps = float(video_stream.average_rate)
    frame_interval = 1.0 / fps
    
    frames = []
    differences = []
    prev_frame = None
    next_sample_time = 0.0
    
    try:
        for packet in container.demux(video_stream):
            for frame in packet.decode():
                current_time = float(frame.pts * video_stream.time_base)
                
                if current_time >= next_sample_time:
                    img = frame.to_image().convert('L')
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
    else:
        return top_frames
