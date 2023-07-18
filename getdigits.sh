#!/bin/bash

pic="$1"
if [ -z "$pic" ]; then
   echo "Usage: $0 picpath"
   exit 1
fi

set -e
dir="$(dirname $0)"
timeout 10 ffmpeg -rtsp_transport tcp -i "$CAMURL" -vf "select=eq(pict_type\\,I)" -frames:v 1 "$pic" >/dev/null 2>&1
"$dir/ocr.py" "$pic"
