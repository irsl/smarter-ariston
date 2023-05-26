FROM alpine
RUN apk add python3 py3-pip jq ffmpeg bash py3-numpy py3-opencv py3-requests py3-pycryptodome
RUN pip install imutils pycron
ADD server.py ocr.py getdigits.sh /opt/water/
ENV PATH="$PATH:/opt/water"
ENTRYPOINT ["/opt/water/server.py"]
