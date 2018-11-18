#!/usr/bin/python
import argparse
import tornado
import tornado.ioloop
import tornado.httpclient
import json
import math
import sys
import io
import logging

from PIL import Image, ImageChops, ImageDraw

USER_AGENT = 'RAMMB-Stitch (tornado/Python 3)'

logger = logging.getLogger(__name__)

def determine_zoom_level(resolution, tile_size):
    tiles_needed = math.ceil(resolution / tile_size)
    zoom_needed = int(math.ceil(math.log(tiles_needed) / math.log(2)))
    logger.debug("Given tile size of %s and res of %s, need zoom level %s", tile_size, resolution, zoom_needed)
    return zoom_needed

async def download_image(url, tile_cache=None):
    """Download an image and return it as a PIL image"""
    if tile_cache:
        data = tile_cache.get(url)
        if data:
            return Image.open(io.BytesIO(data))

    logger.info("Downloading image: %s", url)
    http = tornado.httpclient.AsyncHTTPClient()
    hreq = tornado.httpclient.HTTPRequest(url, user_agent=USER_AGENT)
    res = await http.fetch(hreq)

    if tile_cache:
        logger.debug("Storing %s bytes to cache for url %s", len(res.body), url)
        tile_cache.put(url, res.body)
        res.buffer.seek(0)

    return Image.open(res.buffer)

async def download_timestamps(satellite, sector, product, tile_cache=None):
    url = 'http://rammb-slider.cira.colostate.edu/data/json/%s/%s/%s/latest_times.json' % (satellite, sector, product)

    if tile_cache:
        data = tile_cache.get(url)
        if data:
            return json.loads(data)['timestamps_int']

    logger.info("Downloading metadata: %s", url)
    http = tornado.httpclient.AsyncHTTPClient()
    hreq = tornado.httpclient.HTTPRequest(url, user_agent=USER_AGENT)
    res = await http.fetch(hreq)

    if tile_cache:
        logger.debug("Storing %s bytes to cache for url %s", len(res.body), url)
        tile_cache.put(url, res.body, exp=10)
        res.buffer.seek(0)

    return json.load(res.buffer)['timestamps_int']

def select_timestamp(target, options):
    if target == 'latest':
        return options[0]

    try:
        if int(target) in options:
            return int(target)
    except Exception:
        pass

    import dateutil.parser
    target_dt = dateutil.parser.parse(target)
    nopts = [(abs((target_dt - opt).total_seconds()), opt) for opt in options]
    nopts.sort()
    return nopts[0]

def build_image_urls(satellite, sector, product, zoom, timestamp):
    base_url = 'http://rammb-slider.cira.colostate.edu/data/imagery/{date}/{satellite}---{sector}/{product}/{timestamp}/{zoom:02d}/{x:03d}_{y:03d}.png'
    max_x = max_y = 2 ** zoom

    return [base_url.format(
        satellite=satellite,
        sector=sector,
        product=product,
        zoom=zoom,
        timestamp=timestamp,
        date=str(timestamp)[:8],
        x=x, y=y
    ) for x in range(0, max_x) for y in range(0, max_y)]

def stitch(images):
    # Assumes images are column-major squares of same tile_size resolution
    tiles_on_side = int(math.sqrt(len(images)))
    tile_size = images[0].size[0]

    result = Image.new('RGB', (tiles_on_side * tile_size, tiles_on_side * tile_size))
    for y in range(tiles_on_side):
        for x in range(tiles_on_side):
            im = images[y * tiles_on_side + x]
            result.paste(im=im, box=(x * tile_size, y * tile_size))
    return result

filters = {}
def register_filter(name):
    def deco(f):
        filters[name] = f
        return f
    return deco

def apply_filters(img, args):
    if not args.filters:
        return img
    for filter in args.filters.split(','):
        if ':' in filter:
            fname, fargs = filter.split(':', 1)
            fargs = fargs.split('-')
            img = filters[fname](img, args, *fargs)
        else:
            img = filters[filter](img, args)
    return img

@register_filter('scale')
def image_filter_scale(img, args):
    width = args.width
    height = args.height

    assert img.size[0] >= width and img.size[1] >= height
    #shrink_factor = min(width / img.size[0], height / img.size[1])

    img.thumbnail((width, height), Image.ANTIALIAS)
    offset = (
        (width  - img.size[0]) // 2,
        (height - img.size[1]) // 2,
    )

    out_im = Image.new('RGB', (width, height))
    out_im.paste(im=img, box=offset)
    return out_im

@register_filter('trim')
def image_filter_trim(img, args):
    # remove black space around the outside of the image
    bg = Image.new(img.mode, img.size, img.getpixel((0,0)))
    diff = ImageChops.difference(img, bg)
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        return img.crop(bbox)
    return img

@register_filter('add_px_top')
def image_filter_add_px_top(img, args, extra_h):
    extra_h = int(extra_h)
    # add some extrapixels of black to the top of the image for my awesome wm toolbar
    out = Image.new(img.mode, (img.size[0], img.size[1] + extra_h), img.getpixel((0,0)))
    out.paste(im=img, box=(0, extra_h))
    return out

@register_filter('timestamp')
def image_filter_timestamp(img, args):
    timestamp = args._timestamp
    txt = '{} @ {}'.format(args.satellite, args._timestamp)
    draw = ImageDraw.Draw(img)
    txt_w, txt_h = draw.textsize(txt)
    pos = (img.size[0] - txt_w - 10, img.size[1] - txt_h - 10)
    ImageDraw.Draw(img).text(xy=pos, text=txt, fill=(64, 64, 64))
    return img

class LevelDBTileCache:
    def __init__(self, filename):
        import plyvel
        self.db = plyvel.DB(filename, create_if_missing=True)

    def get(self, url):
        return self.db.get(url.encode('utf-8'))

    def put(self, url, data, exp=None):
        if exp:
            return  # don't cache, we can't expire
        self.db.put(url.encode('utf-8'), data)

class MemcachedTileCache:
    def __init__(self, hosts):
        import pylibmc
        logger.debug("Connecting to memcached on %r", hosts)
        self.mc = pylibmc.Client(hosts, binary=True)

    def get(self, url):
        return self.mc.get(url.encode('utf-8'))

    def put(self, url, data, exp=None):
        self.mc.set(url.encode('utf-8'), data, time=exp or 0)

async def build_image(tile_cache, args):
    # Grab metadata and determine what timestamp to build
    timestamps = await download_timestamps(args.satellite, args.sector, args.product, tile_cache=tile_cache)
    timestamp = select_timestamp(args.timestamp, timestamps)

    # Grab a zoom-0 tile to compute tilesize
    urls = build_image_urls(args.satellite, args.sector, args.product, zoom=0, timestamp=timestamp)
    assert len(urls) == 1
    image = await download_image(urls[0], tile_cache=tile_cache)
    assert image.size[0] == image.size[1]
    tile_size = image.size[0]

    # Compute zoom
    zoom = args.zoom if args.zoom is not None else determine_zoom_level(max(args.width, args.height), tile_size)

    # Grab the rest of the URLs, stitch, and save
    urls = build_image_urls(args.satellite, args.sector, args.product, zoom, timestamp)
    images = await tornado.gen.multi([download_image(url, tile_cache=tile_cache) for url in urls])
    stitched = stitch(images)

    args._timestamp = timestamp
    final = apply_filters(stitched, args)

    return final

async def script_main():
    tornado.httpclient.AsyncHTTPClient.configure('tornado.simple_httpclient.SimpleAsyncHTTPClient', max_clients=4)
    parser = argparse.ArgumentParser(description="Download and stitch images from RAMMB-Slider into one large composite")
    parser.add_argument('-s', '--satellite', default='goes-16', help="Which satellite? default: goes-16")
    parser.add_argument('-c', '--sector', default='full_disk', help="Which sector? default: full_disk")
    parser.add_argument('-p', '--product', default='geocolor', help="Which product? default: geocolor")
    parser.add_argument('-t', '--timestamp', default='latest', help="Which timestamp? Finds nearest match from available data, default: latest")
    parser.add_argument('--zoom', type=int, help="Zoom level? Highest detail is 4, lowest is 0")
    parser.add_argument('--width', type=int, default=1920, help="Output width?")
    parser.add_argument('--height', type=int, default=1080, help="Output height?")
    parser.add_argument('--filters', help='Image filters')
    parser.add_argument('--cache-filename', help='LevelDB tile cache filename or "memcached" for 127.0.0.1 memcached')
    parser.add_argument('-d', '--debug', action='store_true', help='Debug logging')
    parser.add_argument('output_path', help="Where to save the output?")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('PIL').setLevel(logging.ERROR)

    tile_cache = None
    if args.cache_filename == 'memcached':
        try:
            tile_cache = MemcachedTileCache(['127.0.0.1'])
        except ImportError:
            pass
    elif args.cache_filename:
        try:
            tile_cache = LevelDBTileCache(args.cache_filename)
        except ImportError:
            pass

    final = await build_image(tile_cache, args)
    final.save(args.output_path)

if __name__ == '__main__':
    tornado.ioloop.IOLoop.current().run_sync(script_main)
