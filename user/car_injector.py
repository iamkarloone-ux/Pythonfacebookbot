# user/car_injector.py
import asyncio
import json
import time
import httpx
import uuid
import base64
import gzip
import orjson
import database as db
import state_manager
import messenger_api
import language_manager as lang
from config import ADMIN_ID

BASE_AUTH = "https://carx-id-prod.carx-online.com/api/auth"
BASE_SYNC = "https://street-prod.carx-online.com/str/v1/client"

# Your Supabase public URLs
CAR_LIST_URL = "https://rznrrywtfiyehwkfntfj.supabase.co/storage/v1/object/public/profiles/carlist.json"
CAR_IMAGES_URL = "https://rznrrywtfiyehwkfntfj.supabase.co/storage/v1/object/public/profiles/car_images.json"

# --- HELPER FUNCTIONS ---

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
    """
    STRICT ENCRYPTION: Uses standard Python json.dumps with zero whitespaces.
    Matches carinject1.py exactly to prevent loading screen hangs in the game client!
    """
    json_str = json.dumps(profile_dict, separators=(',', ':'))
    return "l84l" + base64.b64encode(b"\x00" + gzip.compress(json_str.encode("utf-8"))).decode("utf-8")

async def get_profile_injector(client, email, pwd, dev, carx="", is_target=False):
    payload = {"project": "STREET", "username": email, "password": pwd, "deviceId": dev, "deviceUniqueId": dev}
    r = await client.post(f"{BASE_AUTH}/login", json=payload)
    
    if r.status_code != 200 and is_target:
        reg_r = await client.post(f"{BASE_AUTH}/register", json=payload)
        
        if reg_r.status_code != 200:
            raise Exception(f"CarX Registration Failed: {reg_r.text}")
            
        reg_data = reg_r.json()
        if isinstance(reg_data, dict) and "e" in reg_data:
            err_msg = reg_data["e"].get("message", "Unknown Registration Error")
            raise Exception(f"CarX Registration Rejected: {err_msg}")
            
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
    await client.post(f"{BASE_AUTH}/verify", json={"code": "g4a369"}, headers=h)
    
    r_profiles = await client.get(f"{BASE_SYNC}/profiles", headers=h)
    if r_profiles.status_code != 200:
        raise Exception(f"Failed to fetch profiles from CarX ({r_profiles.status_code}): {r_profiles.text}")
        
    env = r_profiles.json()
    cont = find_compressed_data(env)
    
    if not cont:
        return {"compressed_data": encrypt_payload_strict({"resources":{"soft":{"amount":0}}})}, h
    return cont, h

async def load_db_data_async() -> tuple:
    """
    Downloads raw carlist.json and simple car_images.json.
    Returns them as a tuple (car_registry, car_maps) without mutating any keys!
    """
    try:
        async with httpx.AsyncClient() as client:
            # 1. Download raw game data
            response_list = await client.get(CAR_LIST_URL)
            if response_list.status_code != 200:
                print(f"❌ Failed to download carlist.json: {response_list.status_code}")
                return {}, {}
            
            content = response_list.text.strip()
            if not content.startswith("{"): content = "{" + content
            if not content.endswith("}"): content = content + "}"
            raw_car_data = json.loads(content)

            # 2. Download simple name/image mapping
            car_maps = {}
            response_maps = await client.get(CAR_IMAGES_URL)
            if response_maps.status_code == 200:
                try:
                    car_maps = response_maps.json()
                except Exception:
                    print("⚠️ Warning: Failed to parse car_images.json.")

            # 3. Scan and extract pristine, raw cars from the massive game file
            car_registry = {}
            def scan(d):
                if isinstance(d, dict):
                    for k, v in d.items():
                        if k.isdigit() and isinstance(v, dict) and ("tuning" in v or "body_part_set" in v):
                            car_registry[k] = v
                        else: scan(v)
                elif isinstance(d, list):
                    for item in d: scan(item)
            
            scan(raw_car_data)
            return car_registry, car_maps
            
    except Exception as e:
        print(f"❌ Error loading dynamic car data: {e}")
        return {}, {}

# --- USER FLOWS ---

async def prompt_car_injector(sender_psid: str, user_lang: str):
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    await messenger_api.send_quick_replies(sender_psid, lang.get_text('car_inject_prompt_email', user_lang), replies)
    state_manager.set_user_state(sender_psid, 'awaiting_car_inject_email', lang=user_lang)

async def handle_car_injector_email(sender_psid: str, text: str, user_lang: str):
    email = text.strip()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    if "@" not in email or "." not in email:
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('purchase_invalid_email', user_lang), replies)
        
    await messenger_api.send_quick_replies(sender_psid, lang.get_text('car_inject_prompt_pass', user_lang), replies)
    state_manager.set_user_state(sender_psid, 'awaiting_car_inject_password', email=email, lang=user_lang)

async def handle_car_injector_password(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    password = text.strip()
    
    car_db, car_maps = await load_db_data_async()
    if not car_db:
        await messenger_api.send_text(sender_psid, "❌ No cars found. Please contact the admin.")
        state_manager.clear_user_state(sender_psid)
        return

    await messenger_api.send_text(sender_psid, lang.get_text('car_inject_catalog_header', user_lang))

    # We read display name and image dynamically in-memory without altering the raw car_db
    for car_id, car_data in car_db.items():
        mapping = car_maps.get(car_id, {})
        display_name = mapping.get("name", f"Car ID {car_id}")
        image_url = mapping.get("image_url", "N/A")
        
        car_info = f"🚗 *Car ID: {car_id}*\nModel: {display_name}\n💰 Price: 150 PHP\nSafe Injection: Yes"
        await messenger_api.send_text(sender_psid, car_info)
        
        if image_url and image_url != "N/A":
            await messenger_api.send_image(sender_psid, image_url)
            await asyncio.sleep(0.2)

    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    prompt_choice_msg = lang.get_text('car_inject_prompt_choice', user_lang)
    await messenger_api.send_quick_replies(sender_psid, prompt_choice_msg, replies)
    
    state_manager.set_user_state(
        sender_psid, 
        'awaiting_car_inject_choice', 
        email=state['email'], 
        password=password, 
        lang=user_lang
    )

async def handle_car_selection(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    car_id = text.strip()
    car_db, _ = await load_db_data_async()
    
    if car_id not in car_db:
        return await messenger_api.send_text(sender_psid, lang.get_text('manual_entry_invalid_mod', user_lang))
        
    admin = await db.get_admin_info()
    gcash = admin.get('gcash_number') if admin else "09123963204"
    
    msg = lang.get_text('car_inject_prompt_payment', user_lang).replace('{carId}', car_id).replace('{gcashNumber}', gcash)
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    await messenger_api.send_quick_replies(sender_psid, msg, replies)
    
    state_manager.set_user_state(
        sender_psid, 
        'awaiting_receipt_for_car_injector', 
        email=state['email'], 
        password=state['password'], 
        carId=car_id, 
        lang=user_lang
    )

async def handle_car_receipt_analysis(sender_psid: str, analysis: dict, user_lang: str, image_url: str):
    state = state_manager.get_user_state(sender_psid) or {}
    email = state.get('email')
    password = state.get('password')
    car_id = state.get('carId')
    
    amount_str = str(analysis.get("extracted_info", {}).get("amount", "")).replace(',', '')
    ref_number = str(analysis.get("extracted_info", {}).get("reference_number", "")).strip()
    
    try:
        amount = float(amount_str)
    except ValueError:
        amount = 0.0

    if amount != 150.0 or len(ref_number) != 13 or not ref_number.isdigit():
        print(f"[AI-SCAN-FAILED-INJECTOR] Directing injection job {car_id} to manual admin queue.")
        user_name = await messenger_api.get_user_profile(sender_psid)
        
        admin_alert = (
            f"🚨 MANUAL CAR INJECTION REQUEST (AI FAILED) 🚨\n\n"
            f"User: {user_name} ({sender_psid})\n"
            f"Selected Car ID: {car_id}\n"
            f"📧 Email: `{email}`\n"
            f"🔐 Password: `{password}`\n\n"
            f"Please verify this receipt and process the injection manually:\n"
            f"Image URL: {image_url}"
        )
        await messenger_api.send_text(ADMIN_ID, admin_alert)
        
        wait_msg = lang.get_text('car_inject_manual_queue', user_lang)
        await messenger_api.send_text(sender_psid, wait_msg)
        state_manager.clear_user_state(sender_psid)
        return

    try:
        await db.add_reference(ref_number, sender_psid, 1)
        asyncio.create_task(execute_car_injection(sender_psid, email, password, car_id, user_lang))
        user_name = await messenger_api.get_user_profile(sender_psid)
        await messenger_api.send_text(ADMIN_ID, f"🤖 AUTOMATED CAR INJECTION queued for {user_name}\nCar ID: {car_id}\nEmail: {email}")
        
    except Exception as e:
        if "Duplicate" in str(e):
            await messenger_api.send_text(sender_psid, lang.get_text('error_duplicate_ref', user_lang))
        else:
            await messenger_api.send_text(sender_psid, lang.get_text('error_unexpected_user', user_lang))
            
    state_manager.clear_user_state(sender_psid)

# --- BACKGROUND INJECTION TASK ---

async def execute_car_injection(user_psid: str, email: str, password: str, car_id: str, user_lang: str):
    tgt_dev = uuid.uuid4().hex
    car_db, _ = await load_db_data_async()
    
    try:
        await messenger_api.send_text(user_psid, lang.get_text('car_inject_started_user', user_lang))
        
        async with httpx.AsyncClient(http2=True, timeout=60.0) as client:
            client.headers.update({"User-Agent": "UnityPlayer/6000.0.64f1", "X-Project": "STREET"})
            
            # 1. Fetch Target Profile using our local isolated function
            cont, h = await get_profile_injector(client, email, password, tgt_dev, carx="", is_target=False)
            profile = decrypt_payload(cont["compressed_data"])
            
            # 2. Locate Garage
            garage = profile["cars"]["items"] if ("cars" in profile and "items" in profile["cars"]) else profile
            
            # 3. Anchor-Shift Logic
            existing_keys = sorted([int(k) for k in garage.keys() if k.isdigit()])
            last_id = existing_keys[-1] if existing_keys else 1000
            
            # 4. INJECT PRISTINE CAR DATA: We inject the clean, raw car dict directly (just like carinject1.py)
            # Since we kept display metadata separate in the display loop, the raw car_db is completely untouched!
            injected_car = car_db[car_id]
            
            pushed_id = str(last_id + 1)
            garage[pushed_id] = garage.pop(str(last_id))
            garage[str(last_id)] = injected_car # Inject untouched, compliant car data
            
            # 5. Strict Standard Encryption and Upload
            cont["compressed_data"] = encrypt_payload_strict(profile)
            cont["lastSyncTime"] = int(time.time())
            
            r_up = await client.post(f"{BASE_SYNC}/profiles", json=cont, headers=h)
            
            if r_up.status_code != 200:
                raise Exception(f"Upload rejected by CarX: {r_up.text}")
                
            success_msg = lang.get_text('car_inject_success', user_lang).replace('{carName}', car_db[car_id].get('__desc_id', f'Car {car_id}'))
            await messenger_api.send_text(user_psid, success_msg)
            
    except Exception as e:
        print(f"❌ Car Injection Failed for {user_psid}: {e}")
        fail_msg = lang.get_text('car_inject_failed_user', user_lang)
        await messenger_api.send_text(user_psid, fail_msg)
        
        admin_alert = (
            f"🚨 AUTOMATED CAR INJECTION FAILED 🚨\n\n"
            f"User PSID: {user_psid}\n"
            f"Car ID: {car_id}\n"
            f"Email: `{email}`\n"
            f"Password: `{password}`\n\n"
            f"Error: {e}\n"
            f"Please process this manually for the user."
        )
        await messenger_api.send_text(ADMIN_ID, admin_alert)
