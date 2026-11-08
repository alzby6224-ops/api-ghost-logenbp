import os
import time
import random
import json
import socket
import asyncio
import logging
import uuid
from datetime import datetime
from contextlib import suppress

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from protobuf_decoder.protobuf_decoder import Parser

# Optional deps – login does NOT depend on them anymore
try:
    from google_play_scraper import app as play_scraper
except Exception:
    play_scraper = None

try:
    from Pb2 import MajoRLoGinrEs_pb2, PorTs_pb2, DEcwHisPErMsG_pb2
except Exception:
    MajoRLoGinrEs_pb2 = PorTs_pb2 = DEcwHisPErMsG_pb2 = None

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'
xK, xV = AES_KEY, AES_IV

REGION_LANG = {
    'BD': 'bn', 'IND': 'hi', 'PK': 'ur', 'SG': 'en', 'ID': 'id',
    'ME': 'ar', 'VN': 'vi', 'TW': 'zh', 'CIS': 'ru', 'TH': 'th',
    'EU': 'en', 'US': 'en', 'SAC': 'es', 'LK': 'en', 'BR': 'pt'
}

DEFAULT_HEADERS = {
    'User-Agent': 'UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
    'Connection': 'Keep-Alive',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/x-www-form-urlencoded',
    'X-Unity-Version': '2018.4.12f1',
    'X-GA': 'v1 1',
    'ReleaseVersion': 'OB55'
}

# ---------------------------------------------------------------------------
# Low-level protobuf helpers (exact BoT.py logic)
# ---------------------------------------------------------------------------

def EnV_VaRiAnT(n):
    d = []
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            b |= 0x80
        d.append(b)
        if not n:
            break
    return bytes(d)

def ProToBuF(Fields):
    p = bytearray()
    for f, v in Fields.items():
        if isinstance(v, bool):
            p.extend(EnV_VaRiAnT((f << 3) | 0))
            p.extend(EnV_VaRiAnT(1 if v else 0))
        elif isinstance(v, int):
            p.extend(EnV_VaRiAnT((f << 3) | 0))
            p.extend(EnV_VaRiAnT(v))
        elif isinstance(v, str):
            d = v.encode()
            p.extend(EnV_VaRiAnT((f << 3) | 2))
            p.extend(EnV_VaRiAnT(len(d)))
            p.extend(d)
        elif isinstance(v, (bytes, bytearray)):
            d = bytes(v)
            p.extend(EnV_VaRiAnT((f << 3) | 2))
            p.extend(EnV_VaRiAnT(len(d)))
            p.extend(d)
    return bytes(p)

def Read_VaRiAnT(data, pos):
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos

def Parse_ProToBuF(data):
    fields = {}
    pos = 0
    n = len(data)
    while pos < n:
        try:
            key, pos = Read_VaRiAnT(data, pos)
        except Exception:
            break
        fn = key >> 3
        wt = key & 0x07
        try:
            if wt == 0:
                val, pos = Read_VaRiAnT(data, pos)
            elif wt == 2:
                ln, pos = Read_VaRiAnT(data, pos)
                val = data[pos:pos + ln]
                pos += ln
            elif wt == 5:
                val = data[pos:pos + 4]
                pos += 4
            elif wt == 1:
                val = data[pos:pos + 8]
                pos += 8
            else:
                break
        except Exception:
            break
        fields.setdefault(fn, []).append(val)
    return fields

def Ua():
    return random.choice([
        '4.0.18P6', '4.0.19P7', '4.0.20P1', '4.1.0P3', '4.1.5P2',
        '4.2.1P8', '4.2.3P1', '5.0.1B2', '5.0.2P4', '5.1.0P1',
        '5.2.0B1', '5.2.5P3', '5.3.0B1', '5.3.2P2', '5.4.0P1',
        '5.4.3B2', '5.5.0P1', '5.5.2P3'
    ])

def _quiet_print(*args, **kwargs):
    try:
        with open('console_details.log', 'a', encoding='utf-8') as _log:
            print(*args, file=_log, sep=kwargs.get('sep', ' '), end=kwargs.get('end', '\n'))
    except OSError:
        pass
    print(*args, **kwargs)

# ---------------------------------------------------------------------------
# Packet builders (BoT-compatible)
# ---------------------------------------------------------------------------

def EnC_PacKeT_sync(HeX, K, V):
    return AES.new(K, AES.MODE_CBC, V).encrypt(pad(bytes.fromhex(HeX), 16)).hex()

async def EnC_PacKeT(HeX, K, V):
    return EnC_PacKeT_sync(HeX, K, V)

def EnC_Vr_sync(N):
    if N < 0:
        N = (1 << 64) + N
    H = []
    while True:
        BesTo = N & 127
        N >>= 7
        if N:
            BesTo |= 128
        H.append(BesTo)
        if not N:
            break
    return bytes(H)

async def EnC_Vr(N):
    return EnC_Vr_sync(N)

async def CrEaTe_VarianT(field_number, value):
    field_header = field_number << 3 | 0
    return EnC_Vr_sync(field_header) + EnC_Vr_sync(value)

async def CrEaTe_LenGTh(field_number, value):
    field_header = field_number << 3 | 2
    encoded_value = value.encode() if isinstance(value, str) else value
    return EnC_Vr_sync(field_header) + EnC_Vr_sync(len(encoded_value)) + encoded_value

async def CrEaTe_ProTo(fields):
    packet = bytearray()
    for field, value in fields.items():
        if isinstance(value, dict):
            nested_packet = await CrEaTe_ProTo(value)
            packet.extend(await CrEaTe_LenGTh(field, nested_packet))
        elif isinstance(value, int):
            packet.extend(await CrEaTe_VarianT(field, value))
        elif isinstance(value, str) or isinstance(value, bytes):
            packet.extend(await CrEaTe_LenGTh(field, value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    nested_packet = await CrEaTe_ProTo(item)
                    packet.extend(await CrEaTe_LenGTh(field, nested_packet))
                elif isinstance(item, int):
                    packet.extend(await CrEaTe_VarianT(field, item))
                elif isinstance(item, (str, bytes)):
                    packet.extend(await CrEaTe_LenGTh(field, item))
    return packet

def DecodE_HeX(H):
    F = format(H, 'x')
    if len(F) % 2:
        F = '0' + F
    return F

def GeneRaTePk_sync(Pk_hex, N, K, V):
    PkEnc = EnC_PacKeT_sync(Pk_hex, K, V)
    length_hex = DecodE_HeX(len(PkEnc) // 2)
    ln = len(length_hex)
    if ln == 2:
        HeadEr = N + "000000"
    elif ln == 3:
        HeadEr = N + "00000"
    elif ln == 4:
        HeadEr = N + "0000"
    elif ln == 5:
        HeadEr = N + "000"
    else:
        HeadEr = N + "00000"
    return bytes.fromhex(HeadEr + length_hex + PkEnc)

async def GeneRaTePk(Pk, N, K, V):
    return GeneRaTePk_sync(Pk, N, K, V)

async def JoinTeamCode(team_code, key, iv):
    fields = {
        1: bytes.fromhex("01090a0b121619201d2729"), 2: 40,
        3: bytes.fromhex("01090a0b121619201d2729"), 4: "w\\Z]",
        6: 12, 7: bytes.fromhex("01090a0b121619201d2729"),
        8: "1.132.9", 9: 6, 10: 2,
        11: bytes.fromhex("01090a0b121619201d2729")
    }
    f = {
        1: 4,
        2: {
            4: bytes.fromhex("01090a0b121619201d2729"),
            5: str(team_code), 6: 6, 8: 1, 9: fields,
            11: {1: "IDC1", 2: 99, 3: "ME"}, 13: "ar",
            16: bytes.fromhex("374f521955"),
            20: [
                {1: 3, 2: 360}, {1: 4, 2: 391}, {1: 5, 2: 156},
                {1: 29, 2: 204}, {1: 22, 2: 118}, {1: 14, 2: 139}, {1: 21}
            ],
            27: {1: 2, 2: 4}
        }
    }
    Pk = (await CrEaTe_ProTo(f)).hex()
    return GeneRaTePk_sync(Pk, "0519", key, iv)

async def SendInv(bot_uid, target_uid, key, iv):
    fields = {
        1: 33,
        2: {
            1: int(target_uid), 2: "ME", 3: 1, 4: 1, 6: "yyt",
            7: 330, 8: 1000, 9: 100, 10: "DZ", 12: 1,
            13: int(target_uid), 16: 1,
            17: {2: 159, 4: "y[WW", 6: 11, 8: "1.118.1", 9: 3, 10: 1},
            18: 306, 19: 18, 24: 902000306, 26: {},
            27: {1: 11, 2: int(bot_uid), 3: 999}, 28: {},
            31: {1: 1, 2: 32768}, 32: 32768,
            34: {
                1: int(bot_uid), 2: 8,
                3: "\u0010\u0015\b\n\u000b\u0013\f\u000f\u0011\u0004\u0007\u0002\u0003\r\u000e\u0012\u0001\u0005\u0006"
            }
        }
    }
    Pk = (await CrEaTe_ProTo(fields)).hex()
    return GeneRaTePk_sync(Pk, "0519", key, iv)

async def xGHosT(uid, name, sq, key, iv, lang="en"):
    fields = {
        1: 61,
        2: {
            1: int(uid),
            2: {
                1: int(uid), 2: 1159, 3: name, 5: 12, 6: 9999,
                7: 1, 8: {2: 1, 3: 1}, 9: 3, 10: lang
            },
            3: sq
        }
    }
    Pk = (await CrEaTe_ProTo(fields)).hex()
    return GeneRaTePk_sync(Pk, "0519", key, iv)

async def ExitBot(key, iv):
    fields = {1: 7, 2: {1: 0}}
    Pk = (await CrEaTe_ProTo(fields)).hex()
    return GeneRaTePk_sync(Pk, "0519", key, iv)

# ---------------------------------------------------------------------------
# LOGIN – exact BoT.py flow (proven working)
# ---------------------------------------------------------------------------

def PyL_BoT(access_token, open_id):
    """Exact payload builder from working BoT.py."""
    P = {}
    P[3] = time.strftime("%Y-%m-%d %H:%M:%S")
    P[4] = "free fire"
    P[5] = 1
    P[7] = "1.132.9"
    P[8] = "Android OS 14 / API-34 (UP1A.231005.007/V816.0.15.0.UNQMIXM)"
    P[9] = "Handheld"
    P[10] = "Grameenphone"
    P[11] = "CarrierDataNetwork"
    P[12] = 1666
    P[13] = 750
    P[14] = "352"
    P[15] = "ARM64 FP ASIMD AES | 2400 | 8"
    P[16] = 5563
    P[17] = "Mali-G57 MC2"
    P[18] = "OpenGL ES 3.2 v1.r32p1-01eac0.0a0b917d9265b4c01be9925306306139"
    P[19] = "Google|9cc73f7a-91f6-40f6-87ec-5b67e597eb8c"
    P[20] = "59.152.5.188"
    P[21] = "en"
    P[22] = open_id
    P[23] = "8"
    P[24] = "Handheld"
    P[25] = "Xiaomi 2312DRAABI"
    P[26] = "BD"
    P[29] = access_token
    P[30] = 1
    P[41] = "Grameenphone"
    P[42] = "Cellular"
    P[57] = "7428b253defc164018c604a1ebbfebdf"
    P[60] = 109685
    P[61] = 58294
    P[62] = 797
    P[63] = 18000
    P[64] = 58818
    P[65] = 109685
    P[66] = 58818
    P[67] = 109685
    P[73] = 2
    P[74] = "/data/app/~~cqQgpdMykLQEM3odipXatw==/com.dts.freefireth-G6e5yOt1dtuXG5Ambhj18g==/lib/arm64"
    P[76] = 1
    P[77] = "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/~~cqQgpdMykLQEM3odipXatw==/com.dts.freefireth-G6e5yOt1dtuXG5Ambhj18g==/base.apk"
    P[78] = 3
    P[79] = 2
    P[81] = "64"
    P[83] = "2019121229"
    P[85] = 3
    P[86] = "OpenGLES2"
    P[87] = 4095
    P[88] = 8
    P[89] = b"FwQVTgUPX1UaUllDDwcWCRBpWAUOUgsvA1snWlBaO1kFYg=="
    P[90] = "Dhaka"
    P[91] = "C"
    P[92] = 8043
    P[93] = "android"
    P[94] = "KqsHT4XbSZhqerDNUhjbS3DxG/4+I62zQU2tZFJN91kBUICAlZ5yujshLKvjlk/KiShfKfis8EeB1PMhFHIodWPncZC4fCHYF3TcTwNj95aWY/S3"
    P[95] = 111207
    P[96] = '{"cur_rate":[60,90,120],"support_etc2":false}'
    P[97] = 1
    P[98] = 1
    P[99] = "4"
    P[100] = "4"
    P[102] = "GQ]        e"
    P[103] = 1
    P[104] = 45174
    P[105] = 1
    P[106] = "https://dl-bs.ggpolarbear.com/live/ABHotUpdates/|https://core-bs.ggpolarbear.com/live/ABHotUpdates/|a4332cb1c1a84e51dd77441e4856ed5a"
    P[107] = "1.9393e7b8e53e8aeb"
    return AES.new(xK, AES.MODE_CBC, xV).encrypt(pad(ProToBuF(P), 16))

def Strip_MajorLogin_Prefix(body):
    if len(body) <= 64:
        return body
    try:
        if 8 in Parse_ProToBuF(body):
            return body
    except Exception:
        pass
    try:
        if 8 in Parse_ProToBuF(body[64:]):
            return body[64:]
    except Exception:
        pass
    return body[64:]

def _gv(fields, n):
    v = fields.get(n)
    if v is None:
        return None
    if isinstance(v, list):
        v = v[0]
    return v

def ExtractMajorLogin(ml_resp):
    body = Strip_MajorLogin_Prefix(ml_resp)
    f = Parse_ProToBuF(body)
    jwt_b = _gv(f, 8)
    url_b = _gv(f, 10)
    ts_v = _gv(f, 21)
    key_b = _gv(f, 22)
    iv_b = _gv(f, 23)
    acct_v = _gv(f, 1)
    jwt = None
    if isinstance(jwt_b, bytes):
        try:
            jwt = jwt_b.decode("utf-8")
        except Exception:
            jwt = jwt_b.decode("utf-8", errors="ignore")
    elif isinstance(jwt_b, str):
        jwt = jwt_b
    url = None
    if isinstance(url_b, bytes):
        try:
            url = url_b.decode("utf-8")
        except Exception:
            url = None
    elif isinstance(url_b, str):
        url = url_b
    ts = ts_v if isinstance(ts_v, int) else None
    acct = acct_v if isinstance(acct_v, int) else None
    if not jwt or not isinstance(key_b, bytes) or not isinstance(iv_b, bytes):
        _quiet_print("[ML] missing fields jwt/key/iv")
        return None
    return {
        "jwt": jwt, "url": url, "ts": ts,
        "key": key_b, "iv": iv_b, "account_id": acct
    }

async def GeT_AccEss(uid, password):
    """BoT.py access token – JSON v2 endpoint first."""
    url = "https://100067.connect.garena.com/api/v2/oauth/guest/token:grant"
    headers = {"User-Agent": Ua(), "Content-Type": "application/json; charset=utf-8"}
    body = {
        "client_id": 100067,
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        "client_type": 2,
        "device_id": "",
        "password": str(password),
        "response_type": "token",
        "uid": int(uid)
    }
    async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
        try:
            r = await client.post(url, headers=headers, json=body)
            _quiet_print(f"[{uid}] Get access => {r.status_code}")
            if r.status_code not in (200, 201):
                return None
            J = r.json()
            if J.get("code") != 0:
                _quiet_print(f"[{uid}] access code={J.get('code')}")
                return None
            d = J.get("data", {})
            at, oid = d.get("access_token"), d.get("open_id")
            if not at or not oid:
                return None
            return {"access_token": at, "open_id": oid}
        except Exception as e:
            _quiet_print(f"[{uid}] access err: {e}")
            return None

async def MajorLogin_BoT(payload_bytes):
    url = "https://loginbp.ppmainecoonghj.com/MajorLogin"
    # Note: do NOT send "Authorization: Bearer " (empty) — httpx rejects it.
    # BoT.py used requests which was lenient; we omit the header instead.
    headers = {
        "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "Accept": "*/*",
        "Accept-Encoding": "deflate, gzip",
        "X-GA-SV": str(int(time.time())),
        "X-GA": "v1 1",
        "ReleaseVersion": "OB55",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Unity-Version": "2018.4.12f1"
    }
    async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
        try:
            r = await client.post(url, headers=headers, content=payload_bytes)
            _quiet_print(f"MajorLogin => {r.status_code} len={len(r.content)}")
            if r.status_code in (200, 201) and r.content:
                return r.content
            return None
        except Exception as e:
            _quiet_print(f"MajorLogin err: {e}")
            return None

async def GeTLoginDaTa_BoT(client_url, payload_bytes, jwt):
    url = f"{client_url.rstrip('/')}/GetLoginData"
    headers = {
        "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "Accept": "*/*",
        "Accept-Encoding": "deflate, gzip",
        "X-GA-SV": str(int(time.time())),
        "Authorization": f"Bearer {jwt}",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB55",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Unity-Version": "2018.4.12f1"
    }
    async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
        try:
            r = await client.post(url, headers=headers, content=payload_bytes)
            _quiet_print(f"GetLoginData => {r.status_code} len={len(r.content) if r.content else 0}")
            if r.status_code == 200 and r.content:
                return r.content
            return None
        except Exception as e:
            _quiet_print(f"GetLoginData err: {e}")
            return None

async def loginbp(uid, password, region_pref='ME'):
    """
    Full login using the EXACT working flow from BoT.py.
    Returns dict compatible with GhosTCMD or None + reason logged.
    """
    try:
        td = await GeT_AccEss(uid, password)
        if not td:
            _quiet_print(f"[{uid}] FAIL: access token")
            return None

        access_token = td["access_token"]
        open_id = td["open_id"]
        login_payload = PyL_BoT(access_token, open_id)

        ml = await MajorLogin_BoT(login_payload)
        if not ml:
            _quiet_print(f"[{uid}] FAIL: MajorLogin")
            return None

        ad = ExtractMajorLogin(ml)
        if not ad:
            _quiet_print(f"[{uid}] FAIL: MajorLogin parse")
            return None

        jwt = ad["jwt"]
        ts = ad["ts"] or int(time.time())
        key = ad["key"]
        iv = ad["iv"]
        url = ad["url"] or "https://clientbp.ppmainecoonghj.com"
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        account_id = ad["account_id"]

        _quiet_print(f"[{uid}] JWT len={len(jwt)} | ts={ts} | acct={account_id}")

        ld = await GeTLoginDaTa_BoT(url, login_payload, jwt)
        if not ld:
            _quiet_print(f"[{uid}] FAIL: GetLoginData")
            return None

        gl = Parse_ProToBuF(ld)

        def gv(n):
            v = gl.get(n)
            if v is None:
                return None
            if isinstance(v, list):
                v = v[0]
            return v

        def gs(n):
            v = gv(n)
            return v.decode() if isinstance(v, bytes) else v

        def gi(n):
            v = gv(n)
            return int(v) if isinstance(v, int) else None

        player_name = gs(4) or ""
        func_addr = gs(14)
        info_addr = gs(32)

        if not func_addr or not info_addr:
            _quiet_print(f"[{uid}] FAIL: missing ip:port  func={func_addr} info={info_addr}")
            return None

        ip, port = str(func_addr).split(":")
        ip2, port2 = str(info_addr).split(":")

        if not account_id:
            account_id = gi(1) or gi(5) or 0

        _quiet_print(f"[{uid}] ONLINE | {player_name} | UID={account_id} | chat={ip2}:{port2}")

        return {
            'bot_uid': str(account_id),
            'token': jwt,
            'region': region_pref,
            'key': key,
            'iv': iv,
            'timestamp': ts,
            'online_ip': ip,
            'online_port': port,
            'chat_ip': ip2,
            'chat_port': port2,
            'account_name': player_name,
            'server_url': url
        }
    except Exception as e:
        _quiet_print(f"[{uid}] loginbp EXCEPTION: {e}")
        return None

# ---------------------------------------------------------------------------
# Auth token (BoT format)
# ---------------------------------------------------------------------------

def BuildAuthToken(uid, jwt_str, ts, key, iv, mode="online"):
    ah = f"{int(uid):x}"
    if len(ah) > 16:
        raise ValueError("uid hex too long")
    ah = ah.zfill(16)
    K = bytes.fromhex(key) if isinstance(key, str) else key
    V = bytes.fromhex(iv) if isinstance(iv, str) else iv
    enc = AES.new(K, AES.MODE_CBC, V).encrypt(pad(jwt_str.encode(), 16)).hex()
    th = f"{int(ts):x}"
    if len(th) % 2:
        th = "0" + th
    tsz = f"{len(enc) // 2:02x}"
    pad_ = "00000" if mode == "chat" else "0000000000000"
    return f"9015{ah}{th}{pad_}{tsz}{enc}"

def CrAuThTK(account_id, jwt_token, timestamp, key, iv, mode="online"):
    try:
        return BuildAuthToken(account_id, jwt_token, timestamp, key, iv, mode=mode)
    except Exception as e:
        _quiet_print(f"CrAuThTK err: {e}")
        return None

def xGetFNLToKeN(account_uid, token, kts, key, iv):
    token_bytes = token.encode('utf-8')
    K = bytes.fromhex(key) if isinstance(key, str) else key
    V = bytes.fromhex(iv) if isinstance(iv, str) else iv
    cipher = AES.new(K, AES.MODE_CBC, V)
    enc_token = cipher.encrypt(pad(token_bytes, 16))
    opcode = bytes.fromhex('830c')
    uid_bytes = int(account_uid).to_bytes(8, byteorder='big')
    kts_bytes = int(kts).to_bytes(4, byteorder='big')
    len_bytes = len(enc_token).to_bytes(8, byteorder='big')
    return opcode + uid_bytes + kts_bytes + len_bytes + enc_token

# ---------------------------------------------------------------------------
# Packet decode helpers
# ---------------------------------------------------------------------------

def Fix_PackEt(parsed_results):
    result_dict = {}
    for result in parsed_results:
        field_data = {'wire_type': result.wire_type}
        if result.wire_type in ("varint", "string", "bytes"):
            field_data['data'] = result.data
        elif result.wire_type == 'length_delimited':
            if hasattr(result.data, 'results'):
                field_data["data"] = Fix_PackEt(result.data.results)
            else:
                field_data["data"] = str(result.data)
        result_dict[result.field] = field_data
    return result_dict

def DeCode_PackEt(input_text):
    try:
        parsed_results = Parser().parse(input_text)
        return json.dumps(Fix_PackEt(parsed_results))
    except Exception:
        return None

async def DecodeWhisperMessage(hex_packet):
    if DEcwHisPErMsG_pb2 is None:
        return None
    proto = DEcwHisPErMsG_pb2.DecodeWhisper()
    proto.ParseFromString(bytes.fromhex(hex_packet))
    return proto

async def cHTypE(H):
    return 'Squid' if not H else 'CLan' if H == 1 else 'PrivaTe'

async def EnC_Uid(H, Tp):
    e, H = ([], int(H))
    while H:
        e.append(H & 127 | (128 if H > 127 else 0))
        H >>= 7
    return bytes(e).hex() if Tp == 'Uid' else None

async def xSEndMsg(Msg, Tp, Tp2, id, K, V):
    feilds = {
        1: id, 2: Tp2, 3: Tp, 4: Msg, 5: int(time.time()), 7: 2,
        9: {
            1: 'xBesTo - C4', 2: 902000003, 3: 901048018, 4: 330, 5: 909034009,
            8: 'xBesTo - C4', 10: 1, 11: 1, 13: {1: 2},
            14: {1: 12484827014, 2: 8, 3: '\x10\x15\x08\n\x0b\x13\x0c\x0f\x11\x04\x07\x02\x03\r\x0e\x12\x01\x05\x06'}
        },
        10: 'en', 13: {3: 1}
    }
    Pk = (await CrEaTe_ProTo(feilds)).hex()
    Pk = '080112' + await EnC_Uid(len(Pk) // 2, Tp='Uid') + Pk
    return GeneRaTePk_sync(Pk, '1201', K, V)

async def xSEndMsgsQ(Msg, id, K, V):
    fields = {
        1: id, 2: id, 4: Msg, 5: int(time.time()), 7: 2, 8: 904990072,
        9: {
            1: 'xBe4!sTo - C4', 2: 902000003, 4: 330, 5: 827001005,
            8: 'xBe4!sTo - C4', 10: 1, 11: 1, 13: {1: 2},
            14: {1: 1158053040, 2: 8, 3: '\x10\x15\x08\n\x0b\x15\x0c\x0f\x11\x04\x07\x02\x03\r\x0e\x12\x01\x05\x06'}
        },
        10: 'en', 13: {2: 2, 3: 1}
    }
    Pk = (await CrEaTe_ProTo(fields)).hex()
    Pk = '080112' + await EnC_Uid(len(Pk) // 2, Tp='Uid') + Pk
    return GeneRaTePk_sync(Pk, '1201', K, V)

async def SEndMsG(H, message, Uid, chat_id, key, iv):
    TypE = await cHTypE(H)
    if TypE == 'Squid':
        return await xSEndMsgsQ(message, chat_id, key, iv)
    return await xSEndMsg(message, 2, Uid, Uid, key, iv)

# ---------------------------------------------------------------------------
# GHOST command – BoT flow
# ---------------------------------------------------------------------------

async def GhosTCMD(teamcode, ghost_name, login_data):
    """
    Ghost flow aligned with working BoT.py.
    Requires an ACTIVE in-game team/squad code (room must be open).
    """
    try:
        key = login_data['key']
        iv = login_data['iv']
        uid = str(login_data['bot_uid'])
        token = login_data['token']
        ts = int(login_data['timestamp'])

        servers = []
        if login_data.get('online_ip') and login_data.get('online_port'):
            servers.append((login_data['online_ip'], int(login_data['online_port']), 'online', 'ONLINE'))
        if login_data.get('chat_ip') and login_data.get('chat_port'):
            servers.append((login_data['chat_ip'], int(login_data['chat_port']), 'chat', 'CHAT'))
        if not servers:
            _quiet_print('[GHOST] no servers')
            return False

        def _as_uid(v):
            if v is None:
                return None
            if isinstance(v, bool):
                return None
            if isinstance(v, int):
                return v if v > 10000 else None
            if isinstance(v, str):
                s = v.strip()
                if s.isdigit() and len(s) >= 5:
                    return int(s)
            return None

        def _extract_from_packet(packet):
            t_uid, sq = None, None
            # Primary paths from working BoT.py
            try:
                t_uid = _as_uid(packet.get('5', {}).get('data', {}).get('1', {}).get('data'))
            except Exception:
                t_uid = None
            try:
                sq = packet.get('5', {}).get('data', {}).get('5', {}).get('data', {}).get('31', {}).get('data')
            except Exception:
                sq = None
            if sq is None:
                try:
                    sq = packet.get('5', {}).get('data', {}).get('31', {}).get('data')
                except Exception:
                    sq = None
            # Alternate common shapes
            if t_uid is None:
                try:
                    t_uid = _as_uid(packet.get('1', {}).get('data'))
                except Exception:
                    pass
            if t_uid is None:
                try:
                    t_uid = _as_uid(packet.get('5', {}).get('data', {}).get('2', {}).get('data', {}).get('1', {}).get('data'))
                except Exception:
                    pass
            # Accept sq as int/str/bytes
            if sq is not None and not isinstance(sq, (int, str, bytes, bytearray)):
                sq = None
            if t_uid is not None and str(t_uid) == uid:
                # don't ghost ourselves; keep searching other fields
                pass
            return t_uid, sq

        def _scan_buffer(buf, tag):
            target_uid = None
            squad_code = None
            hex_data = buf.hex()
            # BoT: frames starting with 0500
            for opcode in ('0500', '0519', '0501', '1201'):
                idx = 0
                while True:
                    pos = hex_data.find(opcode, idx)
                    if pos < 0:
                        break
                    if pos % 2 != 0:
                        idx = pos + 1
                        continue
                    frame_hex = hex_data[pos:]
                    if 80 < len(frame_hex) < 16000:
                        body = frame_hex[10:] if len(frame_hex) > 10 else frame_hex
                        try:
                            js = DeCode_PackEt(body)
                            if js:
                                packet = json.loads(js)
                                t_uid, sq = _extract_from_packet(packet)
                                if t_uid and sq is not None and str(t_uid) != uid:
                                    _quiet_print(f'[{tag}] hit opcode={opcode} target={t_uid}')
                                    return t_uid, sq
                        except Exception:
                            pass
                    idx = pos + 4
            # framed reader: 2B opcode + 3B size
            view = buf
            offset = 0
            while offset + 5 <= len(view):
                size = int.from_bytes(view[offset + 2:offset + 5], 'big')
                if size <= 0 or size > 300000:
                    offset += 1
                    continue
                if offset + 5 + size > len(view):
                    break
                payload = view[offset + 5:offset + 5 + size]
                offset += 5 + size
                if len(payload) < 20:
                    continue
                try:
                    js = DeCode_PackEt(payload.hex())
                    if not js:
                        continue
                    packet = json.loads(js)
                    t_uid, sq = _extract_from_packet(packet)
                    if t_uid and sq is not None and str(t_uid) != uid:
                        _quiet_print(f'[{tag}] hit framed target={t_uid}')
                        return t_uid, sq
                except Exception:
                    continue
            return None, None

        async def _try_server(host, port, mode, tag):
            auth_hex = CrAuThTK(int(uid), token, ts, key, iv, mode=mode)
            if not auth_hex:
                _quiet_print(f'[{tag}] auth failed')
                return False
            reader = writer = None
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=12)
                writer.write(bytes.fromhex(auth_hex))
                await writer.drain()
                await asyncio.sleep(0.2)

                # send join a few times like BoT
                join_pkt = await JoinTeamCode(teamcode, key, iv)
                for _ in range(2):
                    writer.write(join_pkt)
                    await writer.drain()
                    await asyncio.sleep(0.05)
                _quiet_print(f'[{tag}] join sent team={teamcode}')

                buf = b''
                target_uid = squad_code = None
                start_t = time.time()
                while time.time() - start_t < 12:
                    try:
                        chunk = await asyncio.wait_for(reader.read(65536), timeout=1.5)
                        if not chunk:
                            break
                        buf += chunk
                        if len(buf) < 40:
                            continue
                        # only log first few
                        if len(buf) < 20000:
                            _quiet_print(f'[{tag}] recv +{len(chunk)}B total={len(buf)} head={chunk[:6].hex()}')
                        t_uid, sq = _scan_buffer(buf, tag)
                        if t_uid and sq is not None:
                            target_uid, squad_code = t_uid, sq
                            break
                    except asyncio.TimeoutError:
                        if buf:
                            t_uid, sq = _scan_buffer(buf, tag)
                            if t_uid and sq is not None:
                                target_uid, squad_code = t_uid, sq
                                break
                        continue
                    except Exception as e:
                        _quiet_print(f'[{tag}] read err: {e}')
                        break

                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
                writer = None

                if not target_uid or squad_code is None:
                    _quiet_print(f'[{tag}] no valid team/squad in packets (team may be empty/closed)')
                    return False

                # phase 2
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=12)
                writer.write(bytes.fromhex(auth_hex))
                await writer.drain()
                await asyncio.sleep(0.3)

                writer.write(await SendInv(uid, target_uid, key, iv))
                await writer.drain()

                for _ in range(3):
                    writer.write(await JoinTeamCode(teamcode, key, iv))
                    await writer.drain()
                    await asyncio.sleep(0.02)

                ghost_pkt = await xGHosT(int(target_uid), ghost_name, squad_code, key, iv)
                for _ in range(3):
                    try:
                        writer.write(ghost_pkt)
                        await writer.drain()
                    except Exception:
                        break
                    await asyncio.sleep(0.02)
                _quiet_print(f'[{tag}] GHOST x3 sent target={target_uid} name={ghost_name}')

                writer.write(await ExitBot(key, iv))
                await writer.drain()
                await asyncio.sleep(0.2)
                return True
            except Exception as e:
                _quiet_print(f'[{tag}] session err: {e}')
                return False
            finally:
                if writer is not None:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass

        for host, port, mode, tag in servers:
            _quiet_print(f'[GHOST] try {tag} {host}:{port} mode={mode}')
            if await _try_server(host, port, mode, tag):
                return True

        _quiet_print('[GHOST] no team data extracted on any server')
        return False
    except Exception as e:
        _quiet_print(f'Ghost Execution Error: {e}')
        return False
