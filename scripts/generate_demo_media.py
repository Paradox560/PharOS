"""Generate a tiny reproducible illustration. No Internet/camera media is used."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'backend' / 'assets' / 'synthetic-traffic.mp4'
W, H, FPS, DURATION = 640, 360, 12, 30


def rect(frame, x, y, width, height, color):
    x, y = int(x), int(y)
    for yy in range(max(0, y), min(H, y + height)):
        start, end = max(0, x), min(W, x + width)
        if end > start:
            frame[(yy * W + start) * 3:(yy * W + end) * 3] = bytes(color) * (end - start)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    command = ['ffmpeg', '-y', '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', f'{W}x{H}', '-framerate', str(FPS), '-i', '-', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-crf', '25', str(OUT)]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for i in range(FPS * DURATION):
        t = i / FPS
        frame = bytearray(bytes((17, 26, 28)) * W * H)
        rect(frame, 0, 110, W, 206, (39, 47, 50))
        rect(frame, 0, 108, W, 2, (112, 132, 115))
        rect(frame, 0, 315, W, 2, (112, 132, 115))
        for y in [175, 245]:
            for x in range(0, W, 50):
                rect(frame, x, y, 24, 2, (102, 115, 110))
        for lane, y in enumerate([139, 209, 279]):
            for n in range(6):
                x = (n * 126 + t * (22 + lane * 6)) % 770 - 65
                if lane == 0 and 8 <= t <= 22 and 180 < x < 300:
                    x = 170 + n % 2 * 52
                rect(frame, x, y, 34, 17, (155, 177, 175))
                rect(frame, x + 6, y + 2, 8, 13, (58, 80, 79))
        if 8 <= t <= 22:
            rect(frame, 290, 145, 68, 29, (204, 165, 78))
            rect(frame, 338, 147, 16, 25, (147, 101, 49))
        # The banner uses a deliberately diagrammatic visual; UI carries text provenance.
        for n in range(8):
            rect(frame, 24 + n * 13, 26, 7, 12 + n * 3, (193, 231, 106))
        proc.stdin.write(frame)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit('ffmpeg failed')
    print(f'Generated synthetic 30 second illustration: {OUT.name} ({OUT.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
