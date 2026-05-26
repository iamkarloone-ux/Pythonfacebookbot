import httpx
import asyncio
import orjson
import base64
import gzip
import time
import uuid

BASE_AUTH = "https://carx-id-prod.carx-online.com/api/auth"
BASE_SYNC = "https://street-prod.carx-online.com/str/v1/client"

def find_compressed_data(d):
    if isinstance(d, dict):
        if "compressed_data" in d: return d
        for v in d.values():
            res = find_compressed_data(v)
            if res: return res
    elif isinstance(d, list):
        for item in d:
            res = find_compressed_data(item)
            if res: return res
    return None

def decrypt_payload(compressed_str):
    return orjson.loads(gzip.decompress(base64.b64decode(compressed_str[4:])[1:]))

def encrypt_payload_strict(profile_dict):
    json_bytes = orjson.dumps(profile_dict)
    return "l84l" + base64.b64encode(b"\x00" + gzip.compress(json_bytes)).decode("utf-8")

async def get_profile(client, email, pwd, dev, carx="", is_target=False):
    payload = {"project": "STREET", "username": email, "password": pwd, "deviceId": dev, "deviceUniqueId": dev}
    r = await client.post(f"{BASE_AUTH}/login", json=payload)
    
    if r.status_code != 200 and is_target:
        reg_r = await client.post(f"{BASE_AUTH}/register", json=payload)
        if reg_r.status_code != 200:
            raise Exception(f"CarX Registration Failed ({reg_r.status_code}): {reg_r.text}")
            
        await client.post(f"{BASE_AUTH}/verify", json={"code": "g4a369"})
        r = await client.post(f"{BASE_AUTH}/login", json=payload)
        
    if r.status_code != 200:
        raise Exception(f"CarX Login Failed ({r.status_code}): {r.text}")
    
    data = r.json()
    token = None
    if isinstance(data, dict):
        token = data.get("d", {}).get("token") or data.get("token")
        
    if not token:
        raise Exception(f"CarX authentication succeeded but no token was returned by the server. Response: {r.text}")
    
    if not carx:
        carx = str(data.get("d", {}).get("userId") or data.get("userId") or "")
        
    h = {"Authorization": f"Bearer {token}", "x-token": token, "X-CarX-Id": carx, "X-Device-Id": dev}
    
    # CORRECTED: Passing the headers=h here is required to validate the session token on CarX
    await client.post(f"{BASE_AUTH}/verify", json={"code": "g4a369"}, headers=h)
    
    r_profiles = await client.get(f"{BASE_SYNC}/profiles", headers=h)
    if r_profiles.status_code != 200:
        raise Exception(f"Failed to fetch profiles from CarX ({r_profiles.status_code}): {r_profiles.text}")
        
    env = r_profiles.json()
    cont = find_compressed_data(env)
    
    if not cont:
        return {"compressed_data": encrypt_payload_strict({"resources":{"soft":{"amount":0}}})}, h
    return cont, h


# --- CLONE FROM STATIC STORAGE SNAPSHOT URL ---
async def execute_clone_from_snapshot(profile_url: str, tgt_email: str, tgt_pass: str):
    tgt_dev = uuid.uuid4().hex
    
    async with httpx.AsyncClient(http2=True, timeout=60.0) as client:
        client.headers.update({"User-Agent": "UnityPlayer/6000.0.64f1", "X-Project": "STREET"})
        
        # 1. Download snapshot JSON from Supabase Storage
        r_snap = await client.get(profile_url)
        if r_snap.status_code != 200:
            raise Exception(f"Failed to download snapshot profile from storage: {r_snap.text}")
        
        try:
            prof_a = r_snap.json()
        except Exception:
            raise Exception("Downloaded snapshot is not a valid JSON file. Please check your Supabase Storage file.")

        # 2. Fetch Target baseline profile
        cont_b, h_b = await get_profile(client, tgt_email, tgt_pass, tgt_dev, carx="", is_target=True)
        prof_b = decrypt_payload(cont_b["compressed_data"])

        # 3. Mirror Identity
        identity = {k: prof_b.get(k) for k in ["profile", "tutorial_state", "location_id", "current_car_id"] if k in prof_b}
        prof_b.update(prof_a)
        prof_b.update(identity)
        
        # 4. Upload back to Target
        cont_b["compressed_data"] = encrypt_payload_strict(prof_b)
        cont_b["lastSyncTime"] = int(time.time())
        
        r_up = await client.post(f"{BASE_SYNC}/profiles", json=cont_b, headers=h_b)
        if r_up.status_code != 200:
            raise Exception(f"Upload failed: {r_up.text}")
            
        return True


# --- DYNAMIC CLONE (OLD FLOW KEEP AS FALLBACK) ---
async def execute_clone(src_email, src_pass, src_dev, src_carx, tgt_email, tgt_pass):
    tgt_dev = uuid.uuid4().hex
    async with httpx.AsyncClient(http2=True, timeout=60.0) as client:
        client.headers.update({"User-Agent": "UnityPlayer/6000.0.64f1", "X-Project": "STREET"})
        cont_a, _ = await get_profile(client, src_email, src_pass, src_dev, src_carx)
        prof_a = decrypt_payload(cont_a["compressed_data"])
        
        cont_b, h_b = await get_profile(client, tgt_email, tgt_pass, tgt_dev, carx="", is_target=True)
        prof_b = decrypt_payload(cont_b["compressed_data"])

        identity = {k: prof_b.get(k) for k in ["profile", "tutorial_state", "location_id", "current_car_id"] if k in prof_b}
        prof_b.update(prof_a)
        prof_b.update(identity)
        
        cont_b["compressed_data"] = encrypt_payload_strict(prof_b)
        cont_b["lastSyncTime"] = int(time.time())
        
        r_up = await client.post(f"{BASE_SYNC}/profiles", json=cont_b, headers=h_b)
        if r_up.status_code != 200:
            raise Exception(f"Upload failed: {r_up.text}")
            
        return True
