RAMMB-Stitch
------------
Generate beautiful desktop backgrounds using images from RAMMB-Slider.

Can be run as a tornado server with memcached for caching. Example URLs:

http://localhost:7000/goes-16.png
http://localhost:7000/himawari.png
http://localhost:7000/himawari.png?width=1920&height=1068&filters=trim,scale,add_px_top:22,timestamp
http://localhost:7000/goes-16.png?sector=mesoscale_01&product=band_13&zoom=0

Can also be run as a script, for quick testing - see args in rammb_stitch.py
