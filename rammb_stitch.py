#!/usr/bin/python
import argparse
import tornado
import tornado.ioloop
import tornado.httpclient
import json
import dateutil.parser
import math
import sys

from PIL import Image, ImageChops

USER_AGENT = 'RAMMB-Stitch (tornado/Python 3)'
TILE_SIZE = None  # pixels of a tile (square), set in main

def determine_zoom_level(resolution):
    tiles_needed = math.ceil(resolution / TILE_SIZE)
    zoom_needed = int(math.ceil(math.log(tiles_needed) / math.log(2)))
    print("Given tile size of %s and res of %s, need zoom level %s" % (TILE_SIZE, resolution, zoom_needed), file=sys.stderr)
    return zoom_needed

async def download_image(url):
    """Download an image and return it as a PIL image"""
    http = tornado.httpclient.AsyncHTTPClient()
    hreq = tornado.httpclient.HTTPRequest(url, user_agent=USER_AGENT)
    res = await http.fetch(hreq)
    return Image.open(res.buffer)

async def download_timestamps(satellite, sector, product):
    url = 'http://rammb-slider.cira.colostate.edu/data/json/%s/%s/%s/latest_times.json' % (satellite, sector, product)
    http = tornado.httpclient.AsyncHTTPClient()
    hreq = tornado.httpclient.HTTPRequest(url, user_agent=USER_AGENT)
    res = await http.fetch(hreq)
    return json.load(res.buffer)['timestamps_int']

def select_timestamp(target, options):
    if target == 'latest':
        return options[0]
    raise ValueError("Only 'latest' timestamp supported")

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
    # Assumes images are column-major squares of TILE_SIZE resolution
    tiles_on_side = int(math.sqrt(len(images)))

    result = Image.new('RGB', (tiles_on_side * TILE_SIZE, tiles_on_side * TILE_SIZE))
    for y in range(tiles_on_side):
        for x in range(tiles_on_side):
            im = images[y * tiles_on_side + x]
            result.paste(im=im, box=(x * TILE_SIZE, y * TILE_SIZE))
    return result

filters = {}
def register_filter(name):
    def deco(f):
        filters[name] = f
        return f
    return deco

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

@register_filter('add_22_px')
def image_filter_plus_22_px(img, args):
    # add 22 pixels of black to the top of the image for my awesome wm toolbars
    extra_h = 22
    out = Image.new(img.mode, (img.size[0], img.size[1] + extra_h), img.getpixel((0,0)))
    out.paste(im=img, box=(0, extra_h))
    return out

def apply_filters(img, args):
    if not args.filters:
        return img
    for filter in args.filters.split(','):
        img = filters[filter](img, args)
    return img

async def main():
    tornado.httpclient.AsyncHTTPClient.configure('tornado.simple_httpclient.SimpleAsyncHTTPClient', max_clients=4)
    parser = argparse.ArgumentParser(description="Download and stitch images from RAMMB-Slider into one large composite")
    parser.add_argument('-s', '--satellite', default='goes-16', help="Which satellite? default: goes-16")
    parser.add_argument('-c', '--sector', default='full_disk', help="Which sector? default: full_disk")
    parser.add_argument('-p', '--product', default='geocolor', help="Which product? default: geocolor")
    parser.add_argument('-t', '--time', default='latest', help="Which timestamp? Finds nearest match from available data, default: latest")
    parser.add_argument('--zoom', type=int, help="Zoom level? Highest detail is 4, lowest is 0")
    parser.add_argument('--width', type=int, default=1920, help="Output width?")
    parser.add_argument('--height', type=int, default=1080, help="Output height?")
    parser.add_argument('--filters', help='Image filters')
    parser.add_argument('output_path', help="Where to save the output?")
    args = parser.parse_args()

    # Grab metadata and determine what timestamp to build
    timestamps = await download_timestamps(args.satellite, args.sector, args.product)
    timestamp = select_timestamp(args.time, timestamps)

    # Grab a zoom-0 tile to compute tilesize
    urls = build_image_urls(args.satellite, args.sector, args.product, zoom=0, timestamp=timestamp)
    assert len(urls) == 1
    image = await download_image(urls[0])
    global TILE_SIZE
    assert image.size[0] == image.size[1]
    TILE_SIZE = image.size[0]

    # Compute zoom
    zoom = int(args.zoom) if args.zoom else determine_zoom_level(max(args.width, args.height))

    # Grab the rest of the URLs, stitch, and save
    urls = build_image_urls(args.satellite, args.sector, args.product, zoom, timestamp)
    images = await tornado.gen.multi([download_image(url) for url in urls])
    stitched = stitch(images)

    final = apply_filters(stitched, args)
    final.save(args.output_path)

if __name__ == '__main__':
    tornado.ioloop.IOLoop.current().run_sync(main)
