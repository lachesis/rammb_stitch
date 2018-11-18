#!/bin/bash
cd $(dirname $0)

# see if we are tethering
wifi=$(nmcli -m tabular device show wlan0 | grep CONNECTION -A1 | tail -1 | tr -d '[:space:]')
echo "wifi: --$wifi--"
[ "$wifi" != "vertigo" ] && [ "$wifi" != "ZincIsAMetal" ] && [ "$wifi" != "zinc.io" ] && exit 0

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
python ./rammb_stitch.py --satellite $satellite --filters trim,scale,add_px_top:22,timestamp --width $h --height $[$w-22] satellite_wallpaper.jpg
feh --no-xinerama --bg-fill satellite_wallpaper.jpg
