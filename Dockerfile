FROM alpine

ARG TZ
ENV TZ=${TZ:-Europe/Budapest}

RUN apk add python3 py3-pip jq ffmpeg bash py3-numpy py3-opencv py3-requests py3-pycryptodome py3-scipy tzdata
RUN cp /usr/share/zoneinfo/$TZ /etc/localtime && echo "$TZ" >  /etc/timezone && apk del tzdata
RUN pip install imutils pycron
ADD index.html oboe-browser.min.js server.py ocr.py getdigits.sh tapo-plug.py /opt/water/
ENV PATH="$PATH:/opt/water"
ENTRYPOINT ["/opt/water/server.py"]
