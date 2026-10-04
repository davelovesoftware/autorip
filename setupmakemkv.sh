#!/bin/sh -eu
set -e -u


cd /tmp

# Download the sdf.bin
echo "Getting sdf.bin..."
wget -q "https://www.makemkv.com/sdf.bin"
mv sdf.bin /.MakeMKV

# Get the MakeMKV key
echo "Getting MakeMKV key from forum..."
wget -q "https://forum.makemkv.com/forum/viewtopic.php?f=5&t=1053"
KEY="$(grep -Po '(?<=<code>).*?(?=<\/code>)' viewtopic.php\?f\=5\&t\=1053)"
echo "Got key: $KEY"

# Enter the key into MakeMKV
echo "Entering MakeMKV key..."
echo "app_key=\"$KEY\"" > /.MakeMKV/settings.conf
echo "app_UpdateEnable=\"0\"" >> /.MakeMKV/settings.conf

# Delete the tmp files
rm viewtopic.php\?f=5\&t=1053
