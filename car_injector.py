# user/car_injector.py
import asyncio
import os
import json
import time
import httpx
import uuid
import database as db
import state_manager
import messenger_api
import language_manager as lang
from config import ADMIN_ID

# Import secure cloner helpers directly (avoids duplicate code!)
from carx_cloner import get_profile, decrypt_payload, encrypt_payload_strict, BASE_SYNC

CAR_DB_FILE = "carlist.json"

def load_db_data() -> dict:
    """Reads carlist.json and extracts available car models."""
    if not os.path.exists(CAR_DB_FILE): 
        return {}
    with open(CAR_DB_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content.startswith("{"): content = "{" + content
        if not content.endswith("}"): content = content + "}"
        try:
            data = json.loads(content)
        except Exception:
            return {}

    car_registry = {}
    def scan(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k.isdigit() and isinstance(v, dict) and ("tuning" in v or "body_part_set" in v):
                    car_registry[k] = v
                else: scan(v)
        elif isinstance(d, list):
            for item in d: scan(item)
    
    scan(data)
    return car_registry

# --- USER FLOWS ---

async def prompt_car_injector(sender_psid: str, user_lang: str):
    """Entry point: Asks for the target account email."""
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
    
    # 1. Load Cars
    car_db = load_db_data()
    if not car_db:
        await messenger_api.send_text(sender_psid, "❌ No cars found in the database. Please contact the admin.")
        state_manager.clear_user_state(sender_psid)
        return

    # 2. Send Header Bubble
    await messenger_api.send_text(sender_psid, lang.get_text('car_inject_catalog_header', user_lang))

    # 3. Send Cars as separate, clean bubbles to bypass 2000-char limit
    for car_id, car_data in car_db.items():
        desc = car_data.get("__desc_id", f"Car ID {car_id}")
        image_url = car_data.get("image_url", "N/A") # Fetches custom image if added in carlist.json
        
        car_info = f"🚗 *Car ID: {car_id}*\nModel: {desc}\n💰 Price: 150 PHP\nSafe Injection: Yes"
        if image_url and image_url != "N/A":
            car_info += f"\n🖼️ Image: {image_url}"
            
        await messenger_api.send_text(sender_psid, car_info)

    # 4. Prompt choice
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
    car_db = load_db_data()
    
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
    """
    Handles receipt scanning. If AI fails, it immediately alerts the admin 
    with the customer's credentials and chosen car, bypassing manual fallback.
    """
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

    # AI SCAN FAILURE: Securely forward to Admin & Ask User to Wait
    if amount != 150.0 or len(ref_number) != 13 or not ref_number.isdigit():
        print(f"[AI-SCAN-FAILED-INJECTOR] Directing injection job {car_id} to manual admin queue.")
        
        user_name = await messenger_api.get_user_profile(sender_psid)
        
        # 1. Alert Admin with exact account login credentials
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
        
        # 2. Tell User they are queued for manual processing
        wait_msg = lang.get_text('car_inject_manual_queue', user_lang)
        await messenger_api.send_text(sender_psid, wait_msg)
        state_manager.clear_user_state(sender_psid)
        return

    # AI SUCCESS: Queue Automated Background Injection
    try:
        await db.add_reference(ref_number, sender_psid, 1) # Add dummy reference
        
        # Start injection in background
        asyncio.create_task(execute_car_injection(sender_psid, email, password, car_id, user_lang))
        
        # Inform Admin
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
    """
    Executes the exact anchor-shift injection from carinject1.py asynchronously.
    """
    tgt_dev = uuid.uuid4().hex
    car_db = load_db_data()
    
    try:
        await messenger_api.send_text(user_psid, lang.get_text('car_inject_started_user', user_lang))
        
        async with httpx.AsyncClient(http2=True, timeout=60.0) as client:
            client.headers.update({"User-Agent": "UnityPlayer/6000.0.64f1", "X-Project": "STREET"})
            
            # 1. Fetch Profile
            cont, h = await get_profile(client, email, password, tgt_dev, carx="", is_target=False)
            profile = decrypt_payload(cont["compressed_data"])
            
            # 2. Locate Garage
            garage = profile["cars"]["items"] if ("cars" in profile and "items" in profile["cars"]) else profile
            
            # 3. Anchor-Shift Logic
            existing_keys = sorted([int(k) for k in garage.keys() if k.isdigit()])
            last_id = existing_keys[-1] if existing_keys else 1000
            
            pushed_id = str(last_id + 1)
            garage[pushed_id] = garage.pop(str(last_id))
            garage[str(last_id)] = car_db[car_id]
            
            # 4. Encrypt and Upload
            cont["compressed_data"] = encrypt_payload_strict(profile)
            cont["lastSyncTime"] = int(time.time())
            
            r_up = await client.post(f"{BASE_SYNC}/profiles", json=cont, headers=h)
            
            if r_up.status_code != 200:
                raise Exception(f"Upload rejected by CarX: {r_up.text}")
                
            # 5. Success Delivery
            success_msg = lang.get_text('car_inject_success', user_lang).replace('{carName}', car_db[car_id].get('__desc_id', f'Car {car_id}'))
            await messenger_api.send_text(user_psid, success_msg)
            
    except Exception as e:
        print(f"❌ Car Injection Failed for {user_psid}: {e}")
        
        # Notify User
        fail_msg = lang.get_text('car_inject_failed_user', user_lang)
        await messenger_api.send_text(user_psid, fail_msg)
        
        # Notify Admin
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
