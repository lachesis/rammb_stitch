RAMMB-Stitch
------------
Generate beautiful desktop backgrounds using images from RAMMB-Slider.

Can be run as a tornado server with memcached for caching. Example URLs:

http://localhost:7000/goes-16.png
http://localhost:7000/himawari.png
http://localhost:7000/himawari.jpg?width=1920&height=1068&filters=trim,scale,add_px_top:22,timestamp
http://localhost:7000/goes-16.jpg?sector=mesoscale_01&product=band_13&zoom=0

Memcached will need to be configured to handle objects _slightly_ larger than 1MB. Add `-I 4m` to your config.

Can also be run as a script, for quick testing - see args in rammb_stitch.py
