#!/usr/bin/env python3

# environment vars you need to adjust:
# TAPOPLUG_IP=10.6.8.113
# TAPO_EMAIL
# TAPO_PASSWORD

#https://github.com/jimhigson/oboe.js/
#https://stackoverflow.com/questions/55100770/python-basehttpserver-stream-json-data-high-cpu

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import sys
import time
import json
import subprocess
import threading
import glob
import sqlite3
import pycron
import signal
from datetime import datetime

LIVE_STREAM_URL=os.getenv("LIVE_STREAM_URL")
LISTEN_PORT=int(os.getenv("LISTEN_PORT") or "80")
DATADIR=os.getenv("DATADIR") or "/tmp"
DB_PATH=os.getenv("DB_PATH") or os.path.join(DATADIR,"water.db")
STATICDIR=os.getenv("STATICDIR") or os.path.dirname(__file__)

CLEAN_OLDER_THAN_DAYS=int(os.getenv("CLEAN_OLDER_THAN_DAYS") or "30")
CLEAN_SLEEP=int(os.getenv("CLEAN_SLEEP") or "86400")

PERIODIC_QUERY_CRON=os.getenv("PERIODIC_QUERY_CRON") or "0 6-23 * * *" # https://github.com/kipe/pycron https://stackoverflow.com/questions/373335/how-do-i-get-a-cron-like-scheduler-in-python

MODE_333 = int(os.getenv("MODE_333") or "0")
if MODE_333:
    PERIODIC_QUERY_CRON = "none"

PERIODIC_ONLY_WHEN_UNUSED=int(os.getenv("PERIODIC_ONLY_WHEN_UNUSED") or "0")
PERIODIC_FOLLOWUP_SLEEP=int(os.getenv("PERIODIC_FOLLOWUP_SLEEP") or "300")

TEMPORARY_DISPLAYBOX = (os.getenv("TEMPORARY_DISPLAYBOX") or "0") == "1"
TAPOPLUG_IP=os.environ["TAPOPLUG_IP"]

GETDIGITS_PATH = os.path.join(os.path.dirname(__file__),"getdigits.sh")
TAPOPLUG_PATH = os.path.join(os.path.dirname(__file__),"tapo-plug.py")
static_extensions = {
    ".html": "text/html",
    ".js": "application/javascript",
}

tlock = threading.Lock()

followup_thread = None

def eprint(*args, **kwargs):
    today = datetime.now()
    iso_date = today.isoformat()
    print("["+iso_date+"]", *args, **kwargs, file=sys.stderr)

def cleanup_thread():
    p = os.path.join(DATADIR, "water-*.png")
    while True:
        eprint("Running datadir cleanup")
        now = int(time.time())
        for f in glob.glob(p):
            try:
                s = os.stat(f)
                age_seconds = now - s.st_mtime
                age_days = age_seconds / 86400
                if age_days >= CLEAN_OLDER_THAN_DAYS:
                    eprint("Removing", f)
                    os.unlink(f)
            except:
                pass
        time.sleep(CLEAN_SLEEP)
        
def followup_logic():
    global followup_thread
    eprint("New follow up thread started")
    while True:
        time.sleep(PERIODIC_FOLLOWUP_SLEEP)
        r = (None,)
        try:
            eprint("Followup query attempt...")
            r = query_temperature()
        except:
            pass
        if not r[0]:
            # it was unsuccessful, time to terminate
            eprint("Follow up thread did not manage to query the temperature, terminating")
            followup_thread = None
            break

def _query_temperature_locked(restart_is_fine = False, callback = None, save_pix = False):
    global followup_thread
    def acallback(msg):
        eprint(msg)
        if not callback: return
        callback(msg)

    eprint("_query_temperature_locked", restart_is_fine, callback is None, save_pix)
    result = None
    now = int(time.time())
    b_full_picture = f"water-full-{now}.png"
    full_picture = os.path.join(DATADIR, b_full_picture)
    b_display_box = f"water-display-{now}.png"
    display_box = os.path.join(DATADIR, b_display_box)

    env = {**os.environ}
    if save_pix:
        env["SAVE_DISPLAY_PATH"] = display_box
    acallback("Running getdigits")
    eprint(GETDIGITS_PATH, full_picture)
    p = subprocess.Popen([GETDIGITS_PATH, full_picture], env=env, stdout=subprocess.PIPE, start_new_session=True)
    try:
        (p_stdout, p_stderr) = p.communicate()
    except:
        p.returncode = 143 # timeout
    if not save_pix:
        os.unlink(full_picture)
    
    if p.returncode == 0:
        result = json.loads(p_stdout)[0]
        if result and not MODE_333 and not followup_thread:
            # time to kick off a follow up thread
            followup_thread = threading.Thread(target=followup_logic, args=())
            followup_thread.start()

    if p.returncode != 0:
        acallback("Error running the command...")
    elif not result:
        acallback("Failed reading the digits...")

    if save_pix:
        acallback("image: "+b_display_box)

    if (p.returncode != 0 or not result) and restart_is_fine:
        acallback("Restarting the heater...")
        myenv = dict(os.environ)
        if restart_is_fine == "unused":
            myenv["TAPO_ONLY_WHEN_UNUSED"] = "1"
        p = subprocess.run([TAPOPLUG_PATH, TAPOPLUG_IP, "off", "on"], env=myenv)
        if p.returncode != 0:
            acallback("Failed to restart the heater...")
            return (result, b_full_picture, b_display_box, now)
        acallback("Heater restarted...")
        # Waiting a few seconds as it displays 88 at start
        time.sleep(3)
        return _query_temperature_locked(False, callback, save_pix)

    if MODE_333 and result == 33:
        eprint("display shows 33, ignoring")
        result = None

    return (result, b_full_picture, b_display_box, now)

def _query_temperature(restart_is_fine = False, callback = None, save_pix = False):
    tlock.acquire()
    try:
        re = _query_temperature_locked(restart_is_fine, callback, save_pix)        
        if re[0]:
            # need to persist the data into the db
            pass
        return re
    finally:
        tlock.release()
        
def query_temperature(restart_is_fine = False, callback = None, save_pix = False):
    r = _query_temperature(restart_is_fine, callback, save_pix)
    temp = r[0]
    if temp:
        now = r[3]
        eprint("Persisting result", now, temp)
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO temperature (ts, temp) VALUES(?,?)", (now, temp))
        db.commit()
    return r



class StreamServer(BaseHTTPRequestHandler):

    def _send_chunk(self, data=None):
        jsonstr = json.dumps(data)+"\n" if data else ""
        l = len(jsonstr)
        self.wfile.write('{:X}\r\n{}\r\n'.format(l, jsonstr).encode())

    def _serve_file(self, basedir, content_type):
        f = basedir + self.path
        try:
            file_stats = os.stat(f)
        except:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.send_header("Content-Length", str(file_stats.st_size))
        self.end_headers()
        with open(f, "rb") as f:
            data = f.read()
            self.wfile.write(data)
    
    def serve_pic(self):
        return self._serve_file(DATADIR, "image/png")

    def e404(self):
        self.send_response(404)
        self.end_headers()

    def serve_temperature(self):
        def acallback(msg):
            if msg.startswith("image: ") and TEMPORARY_DISPLAYBOX:
                imgpath = "/"+msg[7:]
                self._send_chunk({ "type": "html", "data": f"<img src='{imgpath}'>" })
                return
            self._send_chunk({ "type": "text", "data": msg })

        self.send_response(200)
        self.send_header("Content-type", "application/stream+json")
        self.send_header('Connection', 'keep-alive')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()
        
        content_len = int(self.headers.get('Content-Length'))
        post_body = self.rfile.read(content_len)
        payload={"force": False}
        try:
            payload = json.loads(post_body)
        except:
            pass

        re = query_temperature(restart_is_fine=payload["force"],save_pix=True,callback=acallback)
        self._send_chunk({ "type": "html", "data": f"<a href='{re[1]}'><img src='{re[2]}'></a>" })
        if re[0]:
            self._send_chunk({ "type": "result", "data": re[0] })
        self._send_chunk({ "type": "ready" })
        self._send_chunk()

    def _send_json_response(self, response):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())  
        
    def _fetch_temp(self, limit = None, now = 0):
        if not now:
            now = int(time.time())
        n = now - 3 * 86400
        response = []
        db = get_db()
        for row in db.execute("SELECT ts*1000, temp FROM temperature WHERE ts > ? ORDER BY ts DESC " + (f"LIMIT {limit}" if limit else ""), (n,)):
            response.append({"x":row[0], "y": row[1]})
        return response
    
    def _fetch_energy(self, limit = None, now = 0):
        if not now:
            now = int(time.time())
        n = now - 3 * 86400
        response = []
        db = get_db()
        for row in db.execute("SELECT ts_start*1000, (ts_end-1)*1000, usage/10 FROM energy_data WHERE ts_start > ? ORDER BY ts_start " + (f"LIMIT {limit}" if limit else ""), (n,)):
            response.append({"x":row[0], "y": row[2]})
            response.append({"x":row[1], "y": row[2]})
        return response
    
    def serve_metadata(self):
        db = get_db()
        response = {}
        for row in db.execute("SELECT * FROM metadata"):
            response[row[0]] = row[1]
        self._send_json_response(response)

    def serve_fetch(self, limit = None):
        now = int(time.time())
        temp = self._fetch_temp(limit, now)
        energy = self._fetch_energy(limit, now)
        self._send_json_response({"temp": temp, "energy": energy})
    
    def serve_latest(self):
        r = self._fetch_temp(1)[0]["y"]
        self._send_json_response(r)

    def serve_live(self):
        r = {}
        if LIVE_STREAM_URL:
            r["url"] = LIVE_STREAM_URL
        self._send_json_response(r)
        
    def do_POST(self):
        if self.path == "/temperature":
            self.serve_temperature()
            return
        self.e404()

    def do_GET(self):
        if self.path == "/":
            self.send_response(307)
            self.send_header("Location", "/index.html")
            self.end_headers()
            return

        if self.path == "/live":
            self.serve_live()
            return

        if self.path == "/fetch":
            self.serve_fetch()
            return

        if self.path == "/metadata":
            self.serve_metadata()
            return

        if self.path == "/latest":
            self.serve_latest()
            return

        if self.path.endswith(".png") and "?" not in self.path and ".." not in self.path:
            self.serve_pic()
            return

        if "?" not in self.path and ".." not in self.path:
            for ext in static_extensions.keys():
                if self.path.endswith(ext):
                    return self._serve_file(STATICDIR, static_extensions[ext])

        self.e404()

def get_db():
    return sqlite3.connect(os.path.join(DATADIR, "water.db"))

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS temperature (ts INT, temp INT)")
    cur.execute("CREATE TABLE IF NOT EXISTS energy_data (ts_start INT PRIMARY KEY, ts_end INT, usage INT)")
    cur.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
    db.commit()
    eprint("Database initialized")

def cron_thread():        
    if PERIODIC_QUERY_CRON == "none":
        eprint('Cron feature is disabled')
        return
    eprint('Cron thread started, only_when_unused is: '+str(PERIODIC_ONLY_WHEN_UNUSED))
    only_when_unused = "unused" if PERIODIC_ONLY_WHEN_UNUSED else True
    while True:
        if pycron.is_now(PERIODIC_QUERY_CRON):
            eprint('Running periodic query')
            query_temperature(restart_is_fine=only_when_unused, save_pix=True)
            time.sleep(60)               # The process should take at least 60 sec
                                         # to avoid running twice in one minute
        else:
            time.sleep(15)               # Check again in 15 seconds

def mode333_thread():
    eprint('Mode 333 thread started')
    while True:
        time.sleep(MODE_333)
        while True:
            eprint('Mode 333 query attempt')
            x = query_temperature(restart_is_fine=False, save_pix=True)
            if x[0]:
                eprint('Mode 333 query attempt was successful:', x[0])
                break
            time.sleep(60)

def cron_mode333_thread():
    if MODE_333:
        mode333_thread()
    else:
        cron_thread()

def energy_thread():
    eprint('Energy thread started')
    while True:
        now = int(time.time())
        if now % 3600 < 60:
            eprint('Running energy usage query')
            ts_end = int(now / 3600) * 3600
            ts_start = ts_end - 3600
            try:
                p = subprocess.run([TAPOPLUG_PATH, TAPOPLUG_IP, str(ts_end-2), str(ts_end-1), "60"], stdout=subprocess.PIPE)
                if p.returncode == 0:
                    resp = json.loads(p.stdout)

                    db = get_db()
                    cur = db.cursor()
                    
                    for k in ["today_runtime", "month_runtime", "today_energy", "month_energy"]:
                        v = resp["energy_usage"][k]
                        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES(?,?)", (k, v))

                    dt = datetime.fromtimestamp(ts_end)                    
                    # if the current time is 21:00, then we are interested in the energy usage between 20:00 and 21:00
                    # that means, the slot in the return array should be 20
                    ts_end_hour = dt.hour - 1
                    # unless it is midnight, then we are looking for the energy usage of 23:00 -24:00 from yesterday, slot 23
                    if ts_end_hour < 0:
                        ts_end_hour = 23
                    energy_usages_in_the_last_24h = resp["energy_data"]["data"]
                    while ts_end_hour >= 0:
                        usage = energy_usages_in_the_last_24h[ts_end_hour]
                        eprint("energy usage", ts_start, ts_end, usage)
                        cur.execute("INSERT OR REPLACE INTO energy_data (ts_start, ts_end, usage) VALUES(?,?,?)", (ts_start, ts_end, usage))
                        ts_end_hour -= 1
                        ts_start -= 3600
                        ts_end -= 3600

                    db.commit()
                else:
                    eprint("Failed to read energy data of the heater...")
            except x:
                eprint("error while retrieving energy data", x)
            
            time.sleep(60)               # The process should take at least 60 sec
                                         # to avoid running twice in one minute
        else:
            time.sleep(55)               # Check again later

def main():
    init_db()
    threading.Thread(target=cron_mode333_thread, args=()).start()
    threading.Thread(target=cleanup_thread, args=()).start()
    threading.Thread(target=energy_thread, args=()).start()
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), StreamServer)
    eprint(f"server started on :{LISTEN_PORT}")
    server.serve_forever()


if __name__ == '__main__':
    main()
