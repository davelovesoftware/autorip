FROM ubuntu:26.04 AS base

# Install eject, udev, wget, and MakeMKV/Handbrake runtime dependencies
RUN apt update && apt install -y eject udev wget python3 tini \
# NOTE: libgl1-mesa-dev is a "transitional dummy package" - looks like soon even the dev package won't be supported and makemkv won't be compileable anymore
	libass9 libavcodec62 libbz2-1.0 libc6 libdrm2 libexpat1 libfontconfig1 libfreetype6 libfribidi0 libgl1-mesa-dev \
	libharfbuzz0b libjansson4 liblzma5 libmp3lame0 libnuma1 libogg0 libopus0 libsamplerate0 libspeex1 libtheora1 \
	libturbojpeg0 libva2 libvorbis0a libvpx12 libx11-6 libx264-165 libxml2-16 libssl3t64 zlib1g

# STAGE: build
FROM base AS build

# Build variables
ARG VERSION_HANDBRAKE=1.11.x
ARG VERSION_MAKEMKV=2.0.0
ARG JOB_COUNT=4

# Install MakeMKV/Handbrake build dependencies
RUN apt install -y \
	autoconf automake build-essential cargo cargo-c cmake git libass-dev libavcodec-dev libbz2-dev libc6-dev libdrm-dev \
	libexpat1-dev libfontconfig-dev libfreetype-dev libfribidi-dev libgl1-mesa-dev libharfbuzz-dev libjansson-dev \
	liblzma-dev libmp3lame-dev libnuma-dev libogg-dev libopus-dev libsamplerate0-dev libspeex-dev libssl-dev libtheora-dev \
	libtool libtool-bin libturbojpeg0-dev libva-dev libvorbis-dev libvpx-dev libx11-dev libx264-dev libxml2-dev m4 make \
	meson nasm ninja-build patch pkg-config qtbase5-dev rustc tar zlib1g-dev

# Get Handbrake source
RUN mkdir -p /opt/src && \
	cd /opt/src && \
	git clone --branch $VERSION_HANDBRAKE https://github.com/HandBrake/HandBrake.git

# Get Makemkv source
RUN mkdir -p /opt/src/makemkv && \
	cd /opt/src/makemkv && \
	wget https://www.makemkv.com/download/makemkv-oss-$VERSION_MAKEMKV.tar.gz && \
	wget https://www.makemkv.com/download/makemkv-bin-$VERSION_MAKEMKV.tar.gz && \
	tar -xpf makemkv-oss-$VERSION_MAKEMKV.tar.gz && \
	tar -xpf makemkv-bin-$VERSION_MAKEMKV.tar.gz && \
	mv makemkv-oss-$VERSION_MAKEMKV makemkv-oss && \
	mv makemkv-bin-$VERSION_MAKEMKV makemkv-bin

# Build Handbrake from source
RUN cd /opt/src/HandBrake && \
	./configure --launch-jobs=$JOB_COUNT --launch --disable-gtk --enable-qsv --enable-libdovi --enable-fdk-aac

# Build MakeMKV from source
RUN cd /opt/src/makemkv/makemkv-oss && \
	./configure && \
	make -j$JOB_COUNT install && \
	cd /opt/src/makemkv/makemkv-bin && \
	mkdir tmp && \
	echo "accepted" > tmp/eula_accepted && \
	make -j$JOB_COUNT install

# STAGE: final
FROM base AS final

# Set runtime environment defaults
ENV HANDBRAKE_ARGS="--main-feature --markers --optimize --format av_mp4 -e x265 --multi-pass --turbo --quality 20 --audio-lang-list eng,en-us,en-uk --first-audio --aencoder copy --audio-copy-mask dtshd,dts,aac,ac3 --audio-fallback aac --aq 20 --mixdown 5point1 --subtitle-lang-list eng,en-us,en-uk --first-subtitle --native-language eng --subtitle-burned=none --subtitle-default=none"
ENV OUTPUT_VID_DIR="/mnt/video"
ENV OUTPUT_VID_EXT=".mp4"
ENV PYTHONUNBUFFERED=1

# Copy the MakeMKV and Handbrake executables and generated libs
COPY --from=build /opt/src/HandBrake/build/HandBrakeCLI /usr/bin
COPY --from=build /usr/bin/makemkv* /usr/bin
COPY --from=build /usr/bin/mmgplsrv /usr/bin
COPY --from=build /usr/bin/mmccextr /usr/bin
# NOTE: This relies on specific symlink-inside-folder behavior: https://github.com/moby/moby/issues/40449
COPY --from=build /usr/lib /usr/lib

# Make the opt folder
RUN mkdir -p /opt/autorip

# Copy shell scripts
COPY ./*.sh /opt/autorip
RUN chmod a+x /opt/autorip/*.sh

# Set the MakeMKV key (this is also run during container start to refresh the key)
RUN mkdir /.MakeMKV && \
	chmod a=rwx /.MakeMKV &&\
	/opt/autorip/setupmakemkv.sh && \
	chmod a=rw /.MakeMKV/settings.conf

# Copy the program logic
COPY ./*.py /opt/autorip
RUN chmod a+x /opt/autorip/*.py

# Set startup
WORKDIR /etc/autorip
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/autorip/run.py"]
