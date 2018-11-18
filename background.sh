#!/bin/bash
cd $(dirname $0)

satellite=$SATELLITE
if [ -z "$satellite" ]; then
    utc_hour=$(TZ=UTC date +%_H)
    if (( $utc_hour >= 12 )); then
        satellite=goes-16
    else
        satellite=himawari
    fi
fi
h=1920
w=1080
if [ -z "$BASE_URL" ]; then
    echo "Scraping locally"
    python ./rammb_stitch.py --satellite $satellite --filters trim,scale,add_px_top:22,timestamp --width $h --height $[$w-22] satellite_wallpaper.jpg
else
    echo "Asking remote server to scrape"
    wget "$BASE_URL/$satellite.jpg?width=1920&height=1058&filters=trim,scale,add_px_top:22,timestamp" -O satellite_wallpaper.jpg
fi
feh --no-xinerama --bg-fill satellite_wallpaper.jpg
