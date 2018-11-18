#!/bin/bash
cd $(dirname $0)
satellite=goes-16
utc_hour=$(TZ=UTC date +%_H)
if (( $utc_hour >= 12 )); then
    satellite=goes-16
else
    satellite=himawari
fi
h=1920
w=1080
python ./rammb_stitch.py --satellite $satellite --filters trim,scale,add_22_px --width $h --height $[$w-22] satellite_wallpaper.jpg
feh --no-xinerama --bg-fill satellite_wallpaper.jpg
