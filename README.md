# Autorip

by: Dave Love

A low-overhead automated DVD/BuRay ripper.
Inspired by https://github.com/automatic-ripping-machine/automatic-ripping-machine but designed to be simpler.

## Installation

The only supported installation method is Docker.

Example compose.yml:

```yaml
# Autorip service

services:
  autorip:
    image: XXXX
    user: XXXX:XXXX
    network_mode: none

TODO!!!

```

## Notes

1. Make sure to map udev under `volumes:` like so: `- /run/udev:/run/udev:ro`
2. Make sure to map the optical drive (usually /dev/sr{SOME NUMBER}) under `devices:` like so: `- /dev/sr0:/dev/sr0`
3. MAYBE???? Need to map the serial device correspoding to the optical drive as well: `- /dev/sg0:/dev/sg0`
