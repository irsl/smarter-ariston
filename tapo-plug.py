#!/usr/bin/env python3

import os
import sys

# patched and slightly customized version of PyP100 (https://pip.pypa.io/en/stable/).
import requests
from requests import Session

from base64 import b64encode, b64decode
import hashlib
from Crypto.PublicKey import RSA
import time
import json
from Crypto.Cipher import AES, PKCS1_OAEP, PKCS1_v1_5
import ast
import pkgutil
import uuid
import json


email = os.environ["TAPO_EMAIL"]
password = os.environ["TAPO_PASSWORD"]
delay = int(os.getenv("TAPO_DELAY") or "3")

def eprint(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)


# note: pkcs7.PKCS7Encoder().encode is broken
# https://stackoverflow.com/questions/43199123/encrypting-with-aes-256-and-pkcs7-padding
def pkcs7_pad(input_str, block_len=16):
    return input_str + chr(block_len-len(input_str)%block_len)*(block_len-len(input_str)%16)

def pkcs7_unpad(ct):
    return ct[:-ord(ct[-1])]

class TpLinkCipher:
    def __init__(self, b_arr: bytearray, b_arr2: bytearray):
        self.iv = b_arr2
        self.key = b_arr

    def encrypt(self, data):
        data = pkcs7_pad(data)
        cipher = AES.new(bytes(self.key), AES.MODE_CBC, bytes(self.iv))
        encrypted = cipher.encrypt(data.encode())
        return b64encode(encrypted).decode().replace("\r\n","")

    def decrypt(self, data: str):
        aes = AES.new(bytes(self.key), AES.MODE_CBC, bytes(self.iv))
        pad_text = aes.decrypt(b64decode(data.encode())).decode()
        return pkcs7_unpad(pad_text)

ERROR_CODES = {
	"0": "Success",
	"-1010": "Invalid Public Key Length",
	"-1012": "Invalid terminalUUID",
	"-1501": "Invalid Request or Credentials",
	"1002": "Incorrect Request",
	"-1003": "JSON formatting error "
}

class TapoPlug():
	def __init__ (self, ipAddress, email, password):
		self.ipAddress = ipAddress
		self.terminalUUID = str(uuid.uuid4())

		self.email = email
		self.password = password
		self.session = None
		self.cookie_name = "TP_SESSIONID"

		self.errorCodes = ERROR_CODES

		self.encryptCredentials()
		self.createKeyPair()

	def encryptCredentials(self):
		#Password Encoding
		self.encodedPassword = b64encode(self.password.encode("UTF-8")).decode("UTF-8")

		#Email Encoding
		self.encodedEmail = self.sha_digest_username(self.email)
		self.encodedEmail = b64encode(self.encodedEmail.encode("utf-8")).decode("UTF-8")

	def createKeyPair(self):
		self.keys = RSA.generate(1024)

		self.privateKey = self.keys.exportKey("PEM")
		self.publicKey  = self.keys.publickey().exportKey("PEM")

	def decode_handshake_key(self, key):
		decode: bytes = b64decode(key.encode("UTF-8"))
		decode2: bytes = self.privateKey

		cipher = PKCS1_v1_5.new(RSA.importKey(decode2))
		do_final = cipher.decrypt(decode, None)
		if do_final is None:
			raise ValueError("Decryption failed!")

		b_arr:bytearray = bytearray()
		b_arr2:bytearray = bytearray()

		for i in range(0, 16):
			b_arr.insert(i, do_final[i])
		for i in range(0, 16):
			b_arr2.insert(i, do_final[i + 16])

		return TpLinkCipher(b_arr, b_arr2)

	def sha_digest_username(self, data):
		b_arr = data.encode("UTF-8")
		digest = hashlib.sha1(b_arr).digest()

		sb = ""
		for i in range(0, len(digest)):
			b = digest[i]
			hex_string = hex(b & 255).replace("0x", "")
			if len(hex_string) == 1:
				sb += "0"
				sb += hex_string
			else:
				sb += hex_string

		return sb

	def handshake(self):

		URL = f"http://{self.ipAddress}/app"
		Payload = {
			"method":"handshake",
			"params":{
				"key": self.publicKey.decode("utf-8"),
				"requestTimeMils": 0
			}
		}
		# start new TCP session
		if self.session:
			self.session.close()
		self.session = Session()

		r = self.session.post(URL, json=Payload, timeout=2)

		encryptedKey = r.json()["result"]["key"]
		self.tpLinkCipher = self.decode_handshake_key(encryptedKey)

		try:

			self.cookie = f"{self.cookie_name}={r.cookies[self.cookie_name]}"

		except:
			errorCode = r.json()["error_code"]
			errorMessage = self.errorCodes[str(errorCode)]
			raise Exception(f"Error Code: {errorCode}, {errorMessage}")

	def login(self):
		URL = f"http://{self.ipAddress}/app"
		Payload = {
			"method":"login_device",
			"params":{
				"password": self.encodedPassword,
				"username": self.encodedEmail
			},
			"requestTimeMils": 0,
		}
		headers = {
			"Cookie": self.cookie
		}

		EncryptedPayload = self.tpLinkCipher.encrypt(json.dumps(Payload))

		SecurePassthroughPayload = {
			"method":"securePassthrough",
			"params":{
				"request": EncryptedPayload
			}
		}

		r = self.session.post(URL, json=SecurePassthroughPayload, headers=headers, timeout=2)

		decryptedResponse = self.tpLinkCipher.decrypt(r.json()["result"]["response"])

		try:
			self.token = ast.literal_eval(decryptedResponse)["result"]["token"]
		except:
			errorCode = ast.literal_eval(decryptedResponse)["error_code"]
			errorMessage = self.errorCodes[str(errorCode)]
			raise Exception(f"Error Code: {errorCode}, {errorMessage}")

	def turnOn(self):
		URL = f"http://{self.ipAddress}/app?token={self.token}"
		Payload = {
			"method": "set_device_info",
			"params":{
				"device_on": True
			},
			"requestTimeMils": 0,
			"terminalUUID": self.terminalUUID
		}

		headers = {
			"Cookie": self.cookie
		}

		EncryptedPayload = self.tpLinkCipher.encrypt(json.dumps(Payload))

		SecurePassthroughPayload = {
			"method": "securePassthrough",
			"params": {
				"request": EncryptedPayload
			}
		}

		r = self.session.post(URL, json=SecurePassthroughPayload, headers=headers, timeout=2)

		decryptedResponse = self.tpLinkCipher.decrypt(r.json()["result"]["response"])

		if ast.literal_eval(decryptedResponse)["error_code"] != 0:
			errorCode = ast.literal_eval(decryptedResponse)["error_code"]
			errorMessage = self.errorCodes[str(errorCode)]
			raise Exception(f"Error Code: {errorCode}, {errorMessage}")

	def turnOff(self):
		URL = f"http://{self.ipAddress}/app?token={self.token}"
		Payload = {
			"method": "set_device_info",
			"params":{
				"device_on": False
			},
			"requestTimeMils": 0,
			"terminalUUID": self.terminalUUID
		}

		headers = {
			"Cookie": self.cookie
		}

		EncryptedPayload = self.tpLinkCipher.encrypt(json.dumps(Payload))

		SecurePassthroughPayload = {
			"method": "securePassthrough",
			"params":{
				"request": EncryptedPayload
			}
		}

		r = self.session.post(URL, json=SecurePassthroughPayload, headers=headers, timeout=2)

		decryptedResponse = self.tpLinkCipher.decrypt(r.json()["result"]["response"])

		if ast.literal_eval(decryptedResponse)["error_code"] != 0:
			errorCode = ast.literal_eval(decryptedResponse)["error_code"]
			errorMessage = self.errorCodes[str(errorCode)]
			raise Exception(f"Error Code: {errorCode}, {errorMessage}")

	def getDeviceInfo(self):
		URL = f"http://{self.ipAddress}/app?token={self.token}"
		Payload = {
			"method": "get_device_info",
			"requestTimeMils": 0,
		}

		headers = {
			"Cookie": self.cookie
		}

		EncryptedPayload = self.tpLinkCipher.encrypt(json.dumps(Payload))

		SecurePassthroughPayload = {
			"method":"securePassthrough",
			"params":{
				"request": EncryptedPayload
			}
		}

		r = self.session.post(URL, json=SecurePassthroughPayload, headers=headers)
		decryptedResponse = self.tpLinkCipher.decrypt(r.json()["result"]["response"])

		return json.loads(decryptedResponse)

	def getDeviceName(self):
		data = self.getDeviceInfo()

		if data["error_code"] != 0:
			errorCode = ast.literal_eval(decryptedResponse)["error_code"]
			errorMessage = self.errorCodes[str(errorCode)]
			raise Exception(f"Error Code: {errorCode}, {errorMessage}")
		else:
			encodedName = data["result"]["nickname"]
			name = b64decode(encodedName)
			return name.decode("utf-8")

	def toggleState(self):
		state = self.getDeviceInfo()["result"]["device_on"]
		if state:
			self.turnOff()
		else:
			self.turnOn()


def do_the_job(ip, *states):
    tp = TapoPlug(ip, email, password)
    tp.handshake()
    tp.login()
    remainingStates = len(states)
    eprint(tp.getDeviceInfo(), states)
    for state in states:
        if state == "on":
            tp.turnOn()
        elif state == "off":
            tp.turnOff()
        else:
            raise Exception("invalid state, must be on or off")
        remainingStates-= 1
        if remainingStates:
            time.sleep(delay)
        

if __name__ == "__main__":    
    do_the_job(*sys.argv[1:])
