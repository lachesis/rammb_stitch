import argparse
import io
import json
import logging
import time
import types

import tornado.httpserver
import tornado.ioloop
import tornado.httpclient
import tornado.web

logger = logging.getLogger(__name__)

from rammb_stitch import build_image, MemcachedTileCache

def safe_do(f, v, d=None):
    if v is None:
        return d
    try:
        return f(v)
    except Exception:
        return d

g_tile_cache = None
class StitchHandler(tornado.web.RequestHandler):
    async def get(self, satellite, filetype):
        # Pass through some arguments to the build_image function which must ducktype to argparse output equiv
        # uber-hacky, can't use namedtuple b/c monkeypatching is used to pass actual timestamp to an image filter
        identity = lambda v: v
        POSSIBLE_ARGS = {  # map from arg name to default value and transformer function
            'sector': ('full_disk', str),
            'product': ('geocolor', str),
            'timestamp': ('latest', str),
            'zoom': (None, int),
            'width': (1920, int),
            'height': (1080, int),
            'filters': ('', str),
        }

        kwargs = {k: safe_do(t, self.get_argument(k, None), d) for (k, (d, t)) in POSSIBLE_ARGS.items()}
        args = types.SimpleNamespace(satellite=satellite, **kwargs)
        logger.info("Running stitch with args: %r", args)

        image = await build_image(g_tile_cache, args)

        if filetype == 'jpg':
            filetype = 'jpeg'

        ibytes = io.BytesIO()
        image.save(ibytes, format=filetype)
        self.set_header('Content-type', 'image/%s' % filetype)
        self.write(ibytes.getvalue())

def make_app(args):
    return tornado.web.Application([
        # TODO: add routes that proxy and cache rammb-slider urls with open cors
        (r"/(?P<satellite>[^/]*).(?P<filetype>png|jpg|jpeg)", StitchHandler),
    ], debug=args.debug)

def server_main():
    import logging; logging.basicConfig(format="%(asctime)s:%(levelname)s:%(name)s:%(message)s", level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run the rammb-stitch server")
    parser.add_argument('--memcache-host', nargs='*', action='append',
                        help='Memcache host to use as tile cache, omit for none, repeat for multiple')
    parser.add_argument('-b', '--bind-all', action='store_true', help='Bind external IP (listen on 0.0.0.0)?')
    parser.add_argument('-d', '--debug', action='store_true', help='Debug / autorestart?')
    parser.add_argument('start_port', default=7000, type=int, nargs='?',
                        help="What port should we start on? (default 7000)")
    parser.add_argument('offset_port', default=0, type=int, nargs='?',
                        help="Add this number to the port number (optional)")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('PIL').setLevel(logging.ERROR)
        logging.getLogger('asyncio').setLevel(logging.INFO)

    if args.memcache_host:
        global g_tile_cache
        g_tile_cache = MemcachedTileCache([h[0] for h in args.memcache_host])

    port = args.start_port + args.offset_port
    logger.info("Starting Tornado on port %s", port)

    app = make_app(args)
    http = tornado.httpserver.HTTPServer(app, xheaders=True)
    http.listen(port, address='0.0.0.0' if args.bind_all else '127.0.0.1')
    tornado.ioloop.IOLoop.current().start()

if __name__ == '__main__':
    server_main()
