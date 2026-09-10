#!/usr/bin/env python3
"""Bounded, read-only raster region statistics. JSON request on stdin, result on stdout."""
import hashlib
import io
import json
import math
import os
import stat
import sys
import time
import warnings
from array import array

MAX_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_ROI = 1_000_000
MAX_COMPONENTS = 5000
SECONDS = 12


def integer(x, lo, hi):
    return type(x) is int and lo <= x <= hi


def validate(q):
    keys = {'image_path', 'roi', 'rgb_min', 'rgb_max', 'saturation_min', 'min_area', 'connectivity'}
    if not isinstance(q, dict) or set(q) != keys:
        raise ValueError('Request must contain exactly the seven documented fields')
    if not isinstance(q['image_path'], str) or not os.path.isabs(q['image_path']) or '\0' in q['image_path']:
        raise ValueError('image_path must be an explicitly authorized absolute local path')
    for k, n, lo, hi in [('roi', 4, 0, MAX_PIXELS), ('rgb_min', 3, 0, 255), ('rgb_max', 3, 0, 255)]:
        if not isinstance(q[k], list) or len(q[k]) != n or not all(integer(v, lo, hi) for v in q[k]):
            raise ValueError('Invalid ' + k)
    if any(a > b for a, b in zip(q['rgb_min'], q['rgb_max'])):
        raise ValueError('rgb_min exceeds rgb_max')
    s = q['saturation_min']
    if type(s) not in (int, float) or not math.isfinite(s) or not 0 <= s <= 1:
        raise ValueError('saturation_min must be finite in [0,1]')
    if not integer(q['min_area'], 1, MAX_ROI) or type(q['connectivity']) is not int or q['connectivity'] not in (4, 8):
        raise ValueError('Invalid min_area or connectivity')


def reject_duplicates(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('Duplicate JSON key')
        result[k] = v
    return result


def measure(q):
    validate(q)
    start = time.monotonic()
    def budget():
        if time.monotonic() - start > SECONDS:
            raise ValueError('Measurement time budget exceeded; no partial statistics returned')
    # The descriptor pins one regular file; parent symlinks resolve normally.
    flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(q['image_path'], flags)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ValueError('Input must be a regular file within 32 MiB')
        data = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
        if len(data) > MAX_BYTES or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(data) != before.st_size:
            raise ValueError('File changed while reading or exceeds byte budget')
    from PIL import Image, __version__
    if __version__ != '12.3.0':
        raise ValueError('Requires locked Pillow 12.3.0')
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data), formats=['PNG', 'JPEG']) as im:
            width, height = im.size
            if width * height > MAX_PIXELS or width <= 0 or height <= 0:
                raise ValueError('Image exceeds pixel budget')
            if getattr(im, 'n_frames', 1) != 1:
                raise ValueError('Animated/multiframe images unsupported')
            if im.getexif().get(274, 1) != 1:
                raise ValueError('Nonidentity EXIF orientation unsupported; do not guess display coordinates')
            if im.mode not in ('RGB', 'RGBA', 'L'):
                raise ValueError('Only RGB, RGBA, and grayscale L images supported')
            x0, y0, x1, y1 = q['roi']
            if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                raise ValueError('ROI must be nonempty and contained in image')
            rw, rh = x1-x0, y1-y0
            if rw * rh > MAX_ROI:
                raise ValueError('ROI exceeds 1,000,000 pixels; split explicitly')
            fmt = im.format
            profile = bool(im.info.get('icc_profile'))
            crop = im.crop((x0, y0, x1, y1))
            # PNG tRNS color keys keep RGB/L mode: conversion resolves effective alpha.
            # Crop retains transparency metadata, so off-ROI transparent pixels do not reject an opaque ROI.
            if crop.convert('RGBA').getchannel('A').getextrema() != (255, 255):
                raise ValueError('ROI contains transparency; background-dependent colors unsupported')
            rgb = crop.convert('RGB').tobytes()
    budget()
    mask = bytearray(rw * rh)
    lo, hi, sat = q['rgb_min'], q['rgb_max'], q['saturation_min']
    for p in range(rw * rh):
        if p % 4096 == 0:
            budget()
        r, g, b = rgb[3*p:3*p+3]
        mx, mn = max(r,g,b), min(r,g,b)
        s = (mx-mn)/mx if mx else 0
        mask[p] = int(lo[0] <= r <= hi[0] and lo[1] <= g <= hi[1] and lo[2] <= b <= hi[2] and s >= sat)
    matched = sum(mask)
    components = []
    small_count = small_pixels = total = 0
    for p in range(len(mask)):
        if p % 4096 == 0:
            budget()
        if not mask[p]:
            continue
        total += 1
        if total > MAX_COMPONENTS:
            raise ValueError('Component budget exceeded; tighten ROI/threshold; no partial statistics returned')
        queue = array('I', [p]); mask[p] = 0; head = 0
        sx = sy = 0
        xmin, xmax, ymin, ymax = rw, -1, rh, -1
        rows, cols = {}, {}
        while head < len(queue):
            if head % 4096 == 0:
                budget()
            u = queue[head]; head += 1
            y, x = divmod(u, rw)
            sx += x; sy += y
            xmin=min(xmin,x); xmax=max(xmax,x); ymin=min(ymin,y); ymax=max(ymax,y)
            rows[y]=rows.get(y,0)+1; cols[x]=cols.get(x,0)+1
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    if (dx == 0 and dy == 0) or (q['connectivity'] == 4 and dx != 0 and dy != 0):
                        continue
                    nx, ny = x+dx, y+dy
                    if 0 <= nx < rw and 0 <= ny < rh:
                        v = ny*rw+nx
                        if mask[v]:
                            mask[v] = 0; queue.append(v)
        area=len(queue)
        if area < q['min_area']:
            small_count += 1; small_pixels += area
            continue
        def sections(counts, low, high, offset):
            positions = sorted(set(low + ((high-low)*i)//8 for i in range(9)))
            return [{'coordinate': t+offset, 'matched_pixels': counts.get(t,0)} for t in positions]
        components.append({'id':len(components)+1, 'bbox':[xmin+x0,ymin+y0,xmax+x0+1,ymax+y0+1],
                           'area_pixels':area, 'centroid':[sx/area+x0,sy/area+y0],
                           'fill_ratio':area/((xmax-xmin+1)*(ymax-ymin+1)),
                           'touches_roi_boundary':xmin == 0 or ymin == 0 or xmax == rw-1 or ymax == rh-1,
                           'x_sections':sections(cols,xmin,xmax,x0), 'y_sections':sections(rows,ymin,ymax,y0)})
    limitations = ['Connected regions are not semantic objects: touching objects merge and fragmented objects split.',
                   'Pixel lengths/areas are raster geometry, never chart values, dimensions, counts of claimed items, or tender conclusions.',
                   'RGB thresholds use decoded sample values without ICC/gamma color management; inspect threshold suitability visually.',
                   'Cross sections count matched pixels of this component at nine evenly spaced integer coordinates including both endpoints; gaps are not filled.']
    if not components:
        limitations.append('No retained component; this does not prove absence of the depicted item.')
    if any(c['touches_roi_boundary'] for c in components):
        limitations.append('ROI boundary contact: components may be cropped or include background.')
    return {'status':'measured', 'semantic_assessment':'not_assessed',
            'source':{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'width':width,'height':height,'format':fmt,'icc_profile_present':profile},
            'coordinate_system':'Decoded raster, EXIF orientation 1 only; origin top-left; x right, y down; pixel centers at integer coordinates; bbox/ROI right and bottom exclusive.',
            'config':q,'matched_pixels':matched,'total_components':total,'retained_components':len(components),
            'discarded_small_components':small_count,'discarded_small_pixels':small_pixels,'components':components,'limitations':limitations,
            'budget':{'max_bytes':MAX_BYTES,'max_pixels':MAX_PIXELS,'max_roi_pixels':MAX_ROI,'max_components':MAX_COMPONENTS,'measurement_seconds':SECONDS,'decode_timeout_enforced':False}}


def main():
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError('Request exceeds 16 KiB')
        q = json.loads(raw, object_pairs_hook=reject_duplicates)
        result = measure(q)
        code = 0
    except Exception as exc:
        result = {'status':'rejected','semantic_assessment':'not_assessed','reason':str(exc),'components':[]}
        code = 2
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return code

if __name__ == '__main__':
    sys.exit(main())
