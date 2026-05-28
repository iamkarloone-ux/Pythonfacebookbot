# user/reseller_tool.py
import asyncio
import time
import uuid
import httpx
import json
import base64
import gzip
import orjson
import database as db
import state_manager
import messenger_api
import language_manager as lang
from config import ADMIN_ID
from user.car_injector import get_profile_injector, decrypt_payload, BASE_SYNC, load_db_data_async

# --- LOCAL ENCRYPTION UTILITIES ---

def encrypt_payload_strict_local(profile_dict):
    json_bytes = orjson.dumps(profile_dict)
    return "l84l" + base64.b64encode(b"\x00" + gzip.compress(json_bytes)).decode("utf-8")

# --- USER FLOWS ---

async def prompt_reseller_tool(sender_psid: str, user_lang: str):
    """Entry point: Asks the user for their reseller license key."""
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    msg = (
        "🔑 *Reseller Patcher Tool* 🔑\n\n"
        "To access this tool, please enter your active Reseller License Key.\n\n"
        "Don't have a key? Message the developer to purchase access for 600 PHP/Month:\n"
        "💬 m.me/lark.abalunan.1"
    )
    await messenger_api.send_quick_replies(sender_psid, msg, replies)
    state_manager.set_user_state(sender_psid, 'awaiting_reseller_key', lang=user_lang)

async def handle_reseller_key(sender_psid: str, text: str, user_lang: str):
    key = text.strip()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    license_info = await db.verify_license_key(key)
    if not license_info:
        msg = (
            "❌ Invalid or Expired License Key.\n\n"
            "Please make sure your key is typed correctly. To buy a subscription (600 PHP/Month), contact:\n"
            "💬 m.me/lark.abalunan.1"
        )
        await messenger_api.send_quick_replies(sender_psid, msg, replies)
        return

    await messenger_api.send_text(sender_psid, "✅ License verified successfully!")
    await messenger_api.send_quick_replies(sender_psid, "📧 Enter the target CarX Street account Email:", replies)
    state_manager.set_user_state(sender_psid, 'awaiting_reseller_target_email', license_key=key, lang=user_lang)

async def handle_reseller_email(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    email = text.strip()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    if "@" not in email or "." not in email:
        return await messenger_api.send_quick_replies(sender_psid, "❌ Invalid email format. Try again:", replies)
        
    await messenger_api.send_quick_replies(sender_psid, "🔐 Enter the target account Password:", replies)
    state_manager.set_user_state(
        sender_psid, 
        'awaiting_reseller_target_pass', 
        license_key=state['license_key'], 
        target_email=email, 
        lang=user_lang
    )

async def handle_reseller_password(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    password = text.strip()
    
    # Store complete credentials in state
    state['target_pass'] = password
    await show_reseller_patch_menu(sender_psid, user_lang, state)

async def show_reseller_patch_menu(sender_psid: str, user_lang: str, state: dict):
    """The central hub menu for performing actions on the active customer account."""
    msg = (
        "⚙️ *Reseller Patcher Action Menu* ⚙️\n"
        f"📧 Target: `{state['target_email']}`\n\n"
        "Choose an action to apply:\n\n"
        "1️⃣ : Ban-Safe Pack 1 (10M Silver + 6k Gold)\n"
        "2️⃣ : Ban-Safe Pack 2 (6M Silver + 1k Gold)\n"
        "3️⃣ : Custom Resources (Silver, Gold, XP - with Skips)\n"
        "4️⃣ : Max Nitro (All or Single Vehicle)\n"
        "5️⃣ : Map Region Unlocker (All Areas)\n"
        "6️⃣ : Inject Custom Car\n"
        "7️⃣ : 👥 Use Different Account\n"
        "8️⃣ : 🚪 Exit to Main Menu"
    )
    
    replies = [
        {"title": "1️⃣ Safe Pack 1", "payload": "patch_safe_1"},
        {"title": "2️⃣ Safe Pack 2", "payload": "patch_safe_2"},
        {"title": "3️⃣ Custom", "payload": "patch_custom"},
        {"title": "4️⃣ Max Nitro", "payload": "patch_nitro_menu"},
        {"title": "5️⃣ Map Unlock Only", "payload": "patch_maps"},
        {"title": "6️⃣ Inject Custom Car", "payload": "patch_inject_car"},
        {"title": "7️⃣ Switch Account", "payload": "reseller_switch_account"},
        {"title": "8️⃣ Exit Menu", "payload": "menu"}
    ]
    await messenger_api.send_quick_replies(sender_psid, msg, replies)
    
    # Clean state before saving to prevent duplicate parameter mapping (avoiding TypeError)
    state.pop("state", None)
    state.pop("timestamp", None)
    state_manager.set_user_state(sender_psid, 'awaiting_reseller_patch_choice', **state)

async def handle_reseller_patch_choice(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    choice = text.strip().lower()
    
    choice_map = {
        'patch_safe_1': 'safe_1', '1': 'safe_1',
        'patch_safe_2': 'safe_2', '2': 'safe_2',
        'patch_custom': 'custom', '3': 'custom',
        'patch_nitro_menu': 'nitro_menu', '4': 'nitro_menu',
        'patch_maps': 'maps', '5': 'maps',
        'patch_inject_car': 'inject_car', '6': 'inject_car',
        'reseller_switch_account': 'switch_account', '7': 'switch_account',
        'menu': 'exit_menu', '8': 'exit_menu'
    }
    
    action = choice_map.get(choice)
    if not action:
        return await show_reseller_patch_menu(sender_psid, user_lang, state)
        
    state.pop("state", None)
    state.pop("timestamp", None)

    # ROUTE ACTIONS
    if action == 'exit_menu':
        state_manager.clear_user_state(sender_psid)
        return await menu.show_user_menu(sender_psid, user_lang)
        
    elif action == 'switch_account':
        replies = [{"title": "⬅️ Back", "payload": "patch_again"}]
        await messenger_api.send_quick_replies(sender_psid, "📧 Enter the target CarX Street account Email:", replies)
        state_manager.set_user_state(sender_psid, 'awaiting_reseller_target_email', license_key=state['license_key'], lang=user_lang)
        
    elif action == 'custom':
        replies = [{"title": "Skip ➡️", "payload": "skip_silver"}]
        await messenger_api.send_quick_replies(sender_psid, "💰 Enter the exact amount of Silver to add (or tap Skip):", replies)
        state_manager.set_user_state(sender_psid, 'awaiting_reseller_custom_silver', **state)
        
    elif action == 'nitro_menu':
        msg = (
            "⚡ *Nitro Modification Menu* ⚡\n\n"
            "Do you want to max out nitro on ALL owned cars, or choose a single car?"
        )
        replies = [
            {"title": "⚡ Max All Cars", "payload": "nitro_all"},
            {"title": "🚗 Select Single Car", "payload": "nitro_single"},
            {"title": "⬅️ Cancel", "payload": "patch_again"}
        ]
        await messenger_api.send_quick_replies(sender_psid, msg, replies)
        state_manager.set_user_state(sender_psid, 'awaiting_reseller_nitro_choice', **state)
        
    elif action == 'inject_car':
        await messenger_api.send_text(sender_psid, "⏳ Downloading available vehicle inventory details...")
        car_db, car_maps = await load_db_data_async()
        
        if car_db:
            await messenger_api.send_text(sender_psid, "🏎️ *Available Cars for Injection* 🏎️\nHere are the cars we can inject into the garage right now:")
            for car_id, car_data in car_db.items():
                mapping = car_maps.get(car_id, {})
                display_name = mapping.get("name", f"Car ID {car_id}")
                image_url = mapping.get("image_url", "N/A")
                
                car_info = f"🚗 *Car ID: {car_id}*\nModel: {display_name}\n💰 Price: Reseller Free\nSafe Injection: Yes"
                await messenger_api.send_text(sender_psid, car_info)
                
                if image_url and image_url != "N/A":
                    await messenger_api.send_image(sender_psid, image_url)
                    await asyncio.sleep(0.2)
                    
        replies = [{"title": "⬅️ Cancel", "payload": "patch_again"}]
        await messenger_api.send_quick_replies(sender_psid, "🚗 Enter the exact Car ID to inject (e.g. 1045):", replies)
        state_manager.set_user_state(sender_psid, 'awaiting_reseller_car_id', **state)
        
    else:
        asyncio.create_task(
            execute_reseller_patch_task(
                user_psid=sender_psid,
                email=state['target_email'],
                password=state['target_pass'],
                action=action,
                user_lang=user_lang,
                state_data=state
            )
        )
        await messenger_api.send_text(sender_psid, "⏳ Launching Patcher Engine... Your request has been queued.")

# --- CUSTOM RESOURCE SUB-FLOWS (WITH SKIPS) ---

async def handle_reseller_custom_silver(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    choice = text.strip().lower()
    
    if choice in ['skip_silver', 'skip']:
        silver = 0.0
    else:
        try:
            silver = float(text.strip().replace(',', ''))
        except ValueError:
            return await messenger_api.send_text(sender_psid, "❌ Please enter a valid number for Silver:")
        
    state.pop("state", None)
    state.pop("timestamp", None)
    
    replies = [{"title": "Skip ➡️", "payload": "skip_gold"}]
    await messenger_api.send_quick_replies(sender_psid, "✨ Enter the exact amount of Gold to add (or tap Skip):", replies)
    state_manager.set_user_state(sender_psid, 'awaiting_reseller_custom_gold', silver_val=silver, **state)

async def handle_reseller_custom_gold(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    choice = text.strip().lower()
    
    if choice in ['skip_gold', 'skip']:
        gold = 0
    else:
        try:
            gold = int(text.strip().replace(',', ''))
        except ValueError:
            return await messenger_api.send_text(sender_psid, "❌ Please enter a valid integer or tap Skip:")
        
    state.pop("state", None)
    state.pop("timestamp", None)
    
    replies = [{"title": "Skip ➡️", "payload": "skip_xp"}]
    await messenger_api.send_quick_replies(sender_psid, "📈 Enter the amount of XP to add (or tap Skip):", replies)
    state_manager.set_user_state(sender_psid, 'awaiting_reseller_custom_xp', gold_val=gold, **state)

async def handle_reseller_custom_xp(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    choice = text.strip().lower()
    
    if choice in ['skip_xp', 'skip']:
        xp = 0
    else:
        try:
            xp = int(text.strip().replace(',', ''))
        except ValueError:
            return await messenger_api.send_text(sender_psid, "❌ Please enter a valid integer or tap Skip:")
        
    # Validation Check: If all Silver, Gold, and XP are skipped (all are 0), cancel the patch and loop back to menu
    if state.get('silver_val', 0.0) == 0.0 and state.get('gold_val', 0) == 0 and xp == 0:
        await messenger_api.send_text(sender_psid, "⚠️ All resources skipped. Patch cancelled.")
        
        # Clean custom form data from the state dictionary
        state.pop("silver_val", None)
        state.pop("gold_val", None)
        state.pop("state", None)
        state.pop("timestamp", None)
        return await show_reseller_patch_menu(sender_psid, user_lang, state)

    asyncio.create_task(
        execute_reseller_patch_task(
            user_psid=sender_psid,
            email=state['target_email'],
            password=state['target_pass'],
            action='custom',
            user_lang=user_lang,
            custom_silver=state['silver_val'],
            custom_gold=state['gold_val'],
            custom_xp=xp,
            state_data=state
        )
    )
    await messenger_api.send_text(sender_psid, "⏳ Launching Patcher Engine with custom values... Your request has been queued.")

# --- SELECTIVE NITRO SUB-FLOWS ---

async def handle_reseller_nitro_choice(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    choice = text.strip().lower()
    
    if choice in ['nitro_all', 'all', '1']:
        asyncio.create_task(
            execute_reseller_patch_task(
                user_psid=sender_psid,
                email=state['target_email'],
                password=state['target_pass'],
                action='nitro_all',
                user_lang=user_lang,
                state_data=state
            )
        )
        await messenger_api.send_text(sender_psid, "⏳ Launching Patcher Engine... Your request has been queued.")
        
    elif choice in ['nitro_single', 'single', '2']:
        await messenger_api.send_text(sender_psid, "⏳ Fetching vehicle profile details from account...")
        try:
            dev_id = uuid.uuid4().hex
            async with httpx.AsyncClient(http2=True, timeout=60.0) as client:
                client.headers.update({"User-Agent": "UnityPlayer/6000.0.64f1", "X-Project": "STREET"})
                cont, h = await get_profile_injector(client, state['target_email'], state['target_pass'], dev_id, carx="", is_target=False)
                profile = decrypt_payload(cont["compressed_data"])
                garage = profile["cars"]["items"] if ("cars" in profile and "items" in profile["cars"]) else profile
                owned_cars = [k for k in garage.keys() if k.isdigit() and isinstance(garage[k], dict)]
                
                if not owned_cars:
                    await messenger_api.send_text(sender_psid, "❌ No cars found in this account's garage.")
                    return await show_reseller_patch_menu(sender_psid, user_lang, state)
                
                msg = "🏎️ *Owned Cars List* 🏎️\n\n"
                for c_id in owned_cars:
                    desc_id = garage[c_id].get("__desc_id", "Unknown Vehicle")
                    msg += f"- ID: `{c_id}` : {desc_id}\n"
                msg += "\n👉 Please enter the exact Car ID from the list to apply Max Nitro to:"
                
                replies = [{"title": "⬅️ Cancel", "payload": "patch_again"}]
                await messenger_api.send_quick_replies(sender_psid, msg, replies)
                
                state.pop("state", None)
                state.pop("timestamp", None)
                state_manager.set_user_state(sender_psid, 'awaiting_reseller_single_nitro_id', **state)
        except Exception as e:
            await messenger_api.send_text(sender_psid, f"❌ Failed to load garage: {e}")
            await show_reseller_patch_menu(sender_psid, user_lang, state)
    else:
        # Cancel / Fallback back to menu
        await show_reseller_patch_menu(sender_psid, user_lang, state)

async def handle_reseller_single_nitro_id(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    car_id = text.strip()
    
    asyncio.create_task(
        execute_reseller_patch_task(
            user_psid=sender_psid,
            email=state['target_email'],
            password=state['target_pass'],
            action='nitro_single',
            user_lang=user_lang,
            target_car_id=car_id,
            state_data=state
        )
    )
    await messenger_api.send_text(sender_psid, f"⏳ Patcher running... Applying Max Nitro to Car ID {car_id}.")

# --- CAR INJECTION SUB-FLOWS ---

async def handle_reseller_car_id(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    car_id = text.strip()
    
    car_db, _ = await load_db_data_async()
    if car_id not in car_db:
        return await messenger_api.send_text(sender_psid, "❌ That Car ID is not available in the database. Please check and try again:")
        
    asyncio.create_task(
        execute_reseller_patch_task(
            user_psid=sender_psid,
            email=state['target_email'],
            password=state['target_pass'],
            action='inject_car',
            user_lang=user_lang,
            target_car_id=car_id,
            state_data=state
        )
    )
    await messenger_api.send_text(sender_psid, f"⏳ Patcher running... Injecting Car ID {car_id}.")

# --- BACKGROUND PATCH EXECUTION ENGINE ---

async def execute_reseller_patch_task(
    user_psid: str, email: str, password: str, action: str, user_lang: str, state_data: dict,
    custom_silver: float = 0, custom_gold: int = 0, custom_xp: int = 0, target_car_id: str = ""
):
    try:
        dev_id = uuid.uuid4().hex
        
        async with httpx.AsyncClient(http2=True, timeout=60.0) as client:
            client.headers.update({"User-Agent": "UnityPlayer/6000.0.64f1", "X-Project": "STREET"})
            
            # 1. Fetch target account profile
            cont, h = await get_profile_injector(client, email, password, dev_id, carx="", is_target=False)
            profile = decrypt_payload(cont["compressed_data"])
            
            # 2. Locate Garage
            garage = profile["cars"]["items"] if ("cars" in profile and "items" in profile["cars"]) else profile
            
            summary_actions = []

            # 3. Process Mod Requests (Preserving all original dict structures in-place)
            res = profile.get("resources", {})
            if "experience" not in res or not isinstance(res["experience"], dict):
                res["experience"] = {"amount": 0}
            current_xp = res["experience"].get("amount", 0)
            
            # --- Modification: Ban Safe Pack 1 (10M Silver + 6k Gold) ---
            if action == 'safe_1':
                res.setdefault("soft", {"amount": 0.0})["amount"] += 10000000.0
                res.setdefault("hard", {"amount": 0})["amount"] += 6000
                profile["resources"] = res
                summary_actions.append("💰 Applied Ban-Safe Pack 1 (+10M Silver, +6k Gold)")

            # --- Modification: Ban Safe Pack 2 (6M Silver + 1k Gold) ---
            elif action == 'safe_2':
                res.setdefault("soft", {"amount": 0.0})["amount"] += 6000000.0
                res.setdefault("hard", {"amount": 0})["amount"] += 1000
                profile["resources"] = res
                summary_actions.append("💰 Applied Ban-Safe Pack 2 (+6M Silver, +1k Gold)")

            # --- Modification: Custom Input Values ---
            elif action == 'custom':
                if custom_silver:
                    res.setdefault("soft", {"amount": 0.0})["amount"] += float(custom_silver)
                if custom_gold:
                    res.setdefault("hard", {"amount": 0})["amount"] += int(custom_gold)
                if custom_xp:
                    res["experience"]["amount"] = current_xp + int(custom_xp)
                profile["resources"] = res
                summary_actions.append(f"💰 Custom Resources added: +{custom_silver:,.0f} Silver, +{custom_gold:,} Gold, +{custom_xp:,} XP")

            # --- Modification: Max Nitro (All cars) ---
            elif action in ['nitro', 'nitro_all']:
                owned_cars = [k for k in garage.keys() if k.isdigit() and isinstance(garage[k], dict)]
                if owned_cars:
                    current_timestamp = int(time.time())
                    for c_id in owned_cars:
                        c_res = garage[c_id].setdefault("consumed_resources", {})
                        nitro = c_res.setdefault("nitro", {})
                        nitro["ts"] = current_timestamp
                        nitro["max_amount"] = 20000000
                        nitro["amount"] = 20000000
                    summary_actions.append(f"⚡ Maxed Nitro on {len(owned_cars)} car(s)")

            # --- Modification: Max Nitro (Single selective car) ---
            elif action == 'nitro_single':
                if target_car_id in garage:
                    current_timestamp = int(time.time())
                    c_res = garage[target_car_id].setdefault("consumed_resources", {})
                    nitro = c_res.setdefault("nitro", {})
                    nitro["ts"] = current_timestamp
                    nitro["max_amount"] = 20000000
                    nitro["amount"] = 20000000
                    car_name = garage[target_car_id].get("__desc_id", f"Car {target_car_id}")
                    summary_actions.append(f"⚡ Maxed Nitro on specific Car: {car_name} (ID: {target_car_id})")

            # --- Modification: Map Region Unlocker ---
            elif action == 'maps':
                world_parts = profile.setdefault("game_world_parts", {})
                quests = profile.setdefault("quests", {})
                
                target_regions = ["industrial", "midtown", "suburb", "port", "mountain", "sunset"]
                for r in target_regions:
                    world_parts.setdefault(r, {})["unlocked"] = True
                    
                map_quests = [
                    "move_to_industrial_intro_quest", "move_to_midtown_intro_quest",
                    "move_to_suburb_intro_quest", "move_to_mountain_intro_quest", "move_to_port_intro_quest"
                ]
                for mq in map_quests:
                    quest_node = quests.setdefault(mq, {})
                    quest_node["completed"] = True
                    quest_node["rewarded"] = True
                summary_actions.append("🗺️ Unlocked all map regions and bypassed quests")

            # --- Modification: Inject Custom Car ---
            elif action == 'inject_car':
                car_db, _ = await load_db_data_async()
                existing_keys = sorted([int(k) for k in garage.keys() if k.isdigit()])
                last_id = existing_keys[-1] if existing_keys else 1000
                
                pushed_id = str(last_id + 1)
                garage[pushed_id] = garage.pop(str(last_id))
                garage[str(last_id)] = car_db[target_car_id]
                
                car_name = car_db[target_car_id].get("__desc_id", f"Car {target_car_id}")
                summary_actions.append(f"🚗 Injected untouched {car_name} (ID: {target_car_id}) into garage slot {last_id}")

            # 4. Strictly synchronize internal lastSyncTime (matches original script!)
            current_time = int(time.time())
            profile["lastSyncTime"] = current_time

            # 5. Securely Encrypt and Upload back to CarX Server
            cont["compressed_data"] = encrypt_payload_strict_local(profile)
            
            r_up = await client.post(f"{BASE_SYNC}/profiles", json=cont, headers=h)
            if r_up.status_code != 200:
                raise Exception(f"Upload rejected by CarX sync server: {r_up.text}")
                
            # 6. Success delivery notification
            success_msg = (
                "🎉 *PATCHING COMPLETED SUCCESSFULLY!* 🎉\n\n"
                f"📧 Account: `{email}`\n"
                "Applied modifications:\n" + "\n".join([f"- {act}" for act in summary_actions]) + "\n\n"
                "Please restart your game completely to view changes! Enjoy! 🔥"
            )
            await messenger_api.send_text(user_psid, success_msg)
            
            # --- PERSISTENCE: Loop reseller menu back on completion automatically ---
            await show_reseller_patch_menu(user_psid, user_lang, state_data)
            
    except Exception as e:
        print(f"❌ Reseller Patcher Task failed for {user_psid}: {e}")
        fail_msg = (
            "😔 *Patcher Task Failed.*\n\n"
            "An error occurred while connecting or uploading to the CarX servers.\n"
            "Please double check your credentials and try again."
        )
        await messenger_api.send_text(user_psid, fail_msg)
        
        # Loop back to menu even on fail
        await show_reseller_patch_menu(user_psid, user_lang, state_data)
