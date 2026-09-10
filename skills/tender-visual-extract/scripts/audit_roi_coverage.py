#!/usr/bin/env python3
"""Exact full-raster threshold coverage, not semantic object completeness. JSON stdin/stdout."""
import hashlib
import io
import json
import multiprocessing
import os
import stat
import sys
import time
import warnings
from measure_regions import validate, reject_duplicates, MAX_BYTES, MAX_PIXELS, MAX_ROI

SCAN_SECONDS = 12
WALL_SECONDS = 18
REQUEST_BYTES = 16384


def audit(q, context):
    validate(q)
    began = time.monotonic()
    def deadline():
        if time.monotonic() - began > SCAN_SECONDS:
            raise ValueError('Cooperative full-raster deadline exceeded; coverage is unknown')
    fd = os.open(q['image_path'], os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        a = os.fstat(stream.fileno())
        if not stat.S_ISREG(a.st_mode) or not 0 < a.st_size <= MAX_BYTES:
            raise ValueError('Source must be a nonempty regular file at most 32 MiB')
        data = stream.read(MAX_BYTES + 1)
        b = os.fstat(stream.fileno())
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(a) != identity(b) or len(data) != a.st_size or len(data) > MAX_BYTES:
            raise ValueError('Source changed during bounded read')
    context['source'] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    from PIL import Image, __version__
    if __version__ != '12.3.0':
        raise ValueError('Requires locked Pillow 12.3.0')
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data), formats=['PNG', 'JPEG']) as im:
            w, h = im.size
            if w <= 0 or h <= 0 or w*h > MAX_PIXELS:
                raise ValueError('Source exceeds 16 million decoded pixels')
            context['source'].update(width=w, height=h, format=im.format)
            if getattr(im, 'n_frames', 1) != 1 or im.mode not in ('RGB', 'RGBA', 'L'):
                raise ValueError('Unsupported animation or image mode')
            if im.getexif().get(274, 1) != 1:
                raise ValueError('Nonidentity EXIF orientation unsupported')
            x0,y0,x1,y1 = q['roi']
            if not 0 <= x0 < x1 <= w or not 0 <= y0 < y1 <= h or (x1-x0)*(y1-y0) > MAX_ROI:
                raise ValueError('ROI must fit image, be nonempty and at most 1 million pixels')
            # Unlike ROI-only measurement, coverage requires known effective alpha everywhere.
            rgba = im.convert('RGBA')
            if rgba.getchannel('A').getextrema() != (255, 255):
                raise ValueError('Effective transparency anywhere in full raster; coverage is unknown')
            del rgba
            context['source']['icc_profile_present'] = bool(im.info.get('icc_profile'))
            rgb = im.convert('RGB')
            pixels = rgb.load()
            deadline()
            full = [0, w, h, -1, -1]
            inside = [0, w, h, -1, -1]
            outside = [0, w, h, -1, -1]
            lo,hi,sat = q['rgb_min'],q['rgb_max'],q['saturation_min']
            scanned = 0
            def add(acc,x,y):
                acc[0] += 1
                if x < acc[1]: acc[1] = x
                if y < acc[2]: acc[2] = y
                if x > acc[3]: acc[3] = x
                if y > acc[4]: acc[4] = y
            for y in range(h):
                for x in range(w):
                    if scanned % 4096 == 0: deadline()
                    scanned += 1
                    r,g,b = pixels[x,y]
                    mx,mn = max(r,g,b),min(r,g,b)
                    saturation = (mx-mn)/mx if mx else 0
                    if lo[0] <= r <= hi[0] and lo[1] <= g <= hi[1] and lo[2] <= b <= hi[2] and saturation >= sat:
                        add(full,x,y)
                        add(inside if x0 <= x < x1 and y0 <= y < y1 else outside,x,y)
            deadline()
    def summary(a):
        return {'matched_pixels':a[0], 'bbox':None if a[0] == 0 else [a[1],a[2],a[3]+1,a[4]+1]}
    return {'status':'audited','semantic_assessment':'not_assessed','source':context['source'], 'config':q,
            'coordinate_system':'Decoded raster, EXIF orientation 1 only; top-left origin, x right, y down; integer pixel centers; ROI/bbox right and bottom exclusive.',
            'full_image':summary(full), 'inside_roi':summary(inside), 'outside_roi':summary(outside),
            'outside_matches_present':outside[0] > 0,
            'budget':{'max_bytes':MAX_BYTES,'max_image_pixels':MAX_PIXELS,'max_roi_pixels':MAX_ROI,'scanned_pixels':scanned,'cooperative_seconds':SCAN_SECONDS,'wall_seconds':WALL_SECONDS,'downsampled':False},
            'limitations':['Matched pixels outside ROI can be omitted objects, labels, axes or background; this is not a semantic object count or a tender decision.',
                           'No outside matches does not establish complete visual coverage: other colors, transparent or unselected content cannot be inferred absent.',
                           'min_area and connectivity are retained for request compatibility but never filter coverage pixels; no connected components are computed here.',
                           'Thresholds are inclusive decoded RGB and HSV saturation, identical to region measurement; no ICC/gamma color management.']}


def rejected(reason,source=None):
    return {'status':'rejected','semantic_assessment':'not_assessed','coverage':'unknown','source':source,'reason':reason}


def worker(q, connection):
    context = {}
    try:
        value = audit(q,context)
    except Exception as exc:
        value = rejected(str(exc),context.get('source'))
    try:
        connection.send(value)
    finally:
        connection.close()


def run_bounded(q):
    validate(q)
    ctx = multiprocessing.get_context('spawn')
    receiver, sender = ctx.Pipe(duplex=False)
    child = ctx.Process(target=worker,args=(q,sender),daemon=True)
    child.start();sender.close()
    try:
        if not receiver.poll(WALL_SECONDS):
            return rejected('Hard worker wall deadline exceeded; coverage is unknown')
        try:
            return receiver.recv()
        except EOFError:
            return rejected('Worker terminated without a complete result; coverage is unknown')
    finally:
        receiver.close()
        if child.is_alive():
            child.terminate()
        child.join(timeout=1)
        if child.is_alive():
            child.kill();child.join(timeout=1)


def main():
    try:
        raw = sys.stdin.buffer.read(REQUEST_BYTES + 1)
        if len(raw) > REQUEST_BYTES:
            raise ValueError('Request exceeds 16 KiB')
        q=json.loads(raw,object_pairs_hook=reject_duplicates)
        result=run_bounded(q)
    except Exception as exc:
        result=rejected(str(exc))
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return 0 if result['status']=='audited' else 2

if __name__=='__main__':
    sys.exit(main())
