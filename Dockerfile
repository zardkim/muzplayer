# ---- frontend build ----
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- ffmpeg: only what music needs (decode the library's formats, encode MP3, change volume; the
# null muxer with pcm_s16le decodes a damaged MP3 to measure it: scanner._read_damaged; mpegts for
# radio HLS segments: radio.py), and one frame of a music video on the NAS as a JPEG thumbnail
# (video_thumbs.py: H.264/HEVC/VP8/VP9/MPEG-4 in mp4/mov/mkv/webm/avi, scaled down) ----
# Debian's ffmpeg package would add about 600 MB; this static build is a few MB.
FROM python:3.12-slim AS ffmpeg
ARG FFMPEG_VERSION=7.1.1
# from ffmpeg.org, release signature checked (key FCF986EA15E6E293A5644F10B4322F04D67658D8)
ARG FFMPEG_SHA256=733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential ca-certificates curl xz-utils libmp3lame-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" -o ffmpeg.tar.xz \
 && echo "${FFMPEG_SHA256}  ffmpeg.tar.xz" | sha256sum -c - \
 && tar xf ffmpeg.tar.xz --strip-components=1
RUN ./configure --disable-everything --disable-autodetect --disable-doc --disable-debug --disable-network \
      --disable-ffplay --disable-ffprobe --disable-avdevice --disable-x86asm \
      --enable-static --disable-shared --extra-ldexeflags=-static \
      --enable-libmp3lame --enable-encoder=libmp3lame,pcm_s16le,mjpeg --enable-muxer=mp3,null,image2 \
      --enable-protocol=file,pipe \
      --enable-demuxer=mp3,flac,mov,aac,ogg,wav,asf,ape,aiff,mpegts,matroska,avi \
      --enable-parser=mpegaudio,flac,aac,vorbis,opus,h264,hevc,vp8,vp9,mpeg4video,mpegvideo \
      --enable-decoder=mp3,mp3float,flac,aac,alac,vorbis,opus,wmav1,wmav2,wmapro,wmalossless,ape,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le,pcm_u8,pcm_s16be,pcm_s24be,pcm_s32be,pcm_f32be,h264,hevc,vp8,vp9,mpeg4,mpeg1video,mpeg2video \
      --enable-filter=aresample,aformat,anull,volume,null,scale,format \
 && make -j"$(nproc)" ffmpeg && strip ffmpeg && ./ffmpeg -hide_banner -encoders | grep -q libmp3lame \
 && ./ffmpeg -hide_banner -encoders | grep -q pcm_s16le && ./ffmpeg -hide_banner -muxers | grep -q ' null ' \
 && ./ffmpeg -hide_banner -encoders | grep -q mjpeg && ./ffmpeg -hide_banner -decoders | grep -q ' hevc '

# ---- runtime ----
FROM python:3.12-slim
ARG APP_VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    MUSIC_DIR=/library/music \
    AUDIOBOOK_DIR=/library/audiobook \
    VIDEO_DIR=/library/video \
    DATA_DIR=/data \
    CONF_DIR=/conf \
    STATIC_DIR=/app/static
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist ./static
COPY --from=ffmpeg /src/ffmpeg /usr/local/bin/ffmpeg
RUN mkdir -p /data /conf && command -v setpriv
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]
