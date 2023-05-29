# Ariston water heater smartening

This project allows querying, displaying the temperature of an Ariston water heater - without a WiFi module.
It needs an RTSP capable IP camera and a Tapo smart plug:

![Photo of the setup](https://github.com/irsl/smarter-ariston/blob/main/smarter-ariston.png?raw=true)

The OCR part is heavily based on
https://pyimagesearch.com/2017/02/13/recognizing-digits-with-opencv-and-python/

The Tapo part is heavily based on
https://pip.pypa.io/en/stable/

An example Ansible playbook to deploy it:

```
  - name: water
    docker_container:
      user: 1000:1000
      name: water
      image: ghcr.io/irsl/smarter-ariston
      volumes:
      - /data:/data
      restart_policy: unless-stopped
      env:
        TZ=Europe/Budapest
        TAPOPLUG_IP=10.6.8.113
        TAPO_EMAIL=youremail
        TAPO_PASSWORD=yourpassword
        CAMURL=rtsp://10.6.8.146:8554/w1
        DATADIR=/data
```
