#!/bin/bash
cd $(dirname $0)
source ./client.sh

CACHEPATH=${CACHEPATH:-.$(hostname)_last_sat_dl}
OUTPATH=${OUTPATH:-$(hostname)_satellite_wallpaper.jpg}
FILTERS=${FILTERS:-trim,scale,add_px_top:22,timestamp}

if [ ! -z "$MAX_CACHE_AGE" ]; then
    if ! check_cache_too_old $CACHEPATH; then
        echo "Last download was recent - doing nothing"
        exit 0
    fi
    date +%s > $CACHEPATH
fi

if [ -z "$BASE_URL" ]; then
    echo "Scraping locally"
    python ./rammb_stitch.py --satellite $satellite --filters trim,scale,add_px_top:22,timestamp --width $h --height $[$w-22] $OUTPATH
else
    echo "Asking remote server to scrape"
    fetch_wallpaper
fi
#feh --no-xinerama --bg-fill satellite_wallpaper.jpg
monman --wallpaper  # my custom wallpaper script
