FROM alpine

RUN apk add --no-cache python3 py3-pip jq ffmpeg bash py3-numpy py3-opencv py3-requests py3-pycryptodome py3-scipy tzdata
RUN pip install imutils pycron
ADD index.html oboe-browser.min.js server.py ocr.py getdigits.sh tapo-plug.py /opt/water/
ENV PATH="$PATH:/opt/water"
ENTRYPOINT ["/opt/water/server.py"]
