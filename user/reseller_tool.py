# user/reseller_tool.py
import asyncio
import time
import uuid
import httpx
import database as db
import state_manager
import messenger_api
import language_manager as lang
from config import ADMIN_ID
from user.car_injector import get_profile_injector, decrypt_payload, encrypt_payload_strict, BASE_SYNC, load_db_data_async

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
    
    msg = (
        "⚙️ *Select Patch Action* ⚙️\n\n"
        "Choose what to apply to this profile:\n\n"
        "1️⃣ : Ban-Safe Pack 1 (10M Silver + 6k Gold)\n"
        "2️⃣ : Ban-Safe Pack 2 (6M Silver + 1k Gold)\n"
        "3️⃣ : Custom Resources (Enter own values)\n"
        "4️⃣ : Max Nitro (All owned cars)\n"
        "5️⃣ : Map Region Unlocker (All areas)\n"
        "6️⃣ : Inject Custom Car"
    )
    
    replies = [
        {"title": "1️⃣ Safe Pack 1 (10M/6k)", "payload": "patch_safe_1"},
        {"title": "2️⃣ Safe Pack 2 (6M/1k)", "payload": "patch_safe_2"},
        {"title": "3️⃣ Custom Resources", "payload": "patch_custom"},
        {"title": "4️⃣ Max Nitro Only", "payload": "patch_nitro"},
        {"title": "5️⃣ Map Unlock Only", "payload": "patch_maps"},
        {"title": "6️⃣ Inject Custom Car", "payload": "patch_inject_car"},
        {"title": "⬅️ Back to Menu", "payload": "menu"}
    ]
    await messenger_api.send_quick_replies(sender_psid, msg, replies)
    state_manager.set_user_state(
        sender_psid, 
        'awaiting_reseller_patch_choice', 
        license_key=state['license_key'], 
        target_email=state['target_email'], 
        target_pass=password, 
        lang=user_lang
    )

async def handle_reseller_patch_choice(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    choice = text.strip().lower()
    
    choice_map = {
        'patch_safe_1': 'safe_1', '1': 'safe_1',
        'patch_safe_2': 'safe_2', '2': 'safe_2',
        'patch_custom': 'custom', '3': 'custom',
        'patch_nitro': 'nitro', '4': 'nitro',
        'patch_maps': 'maps', '5': 'maps',
        'patch_inject_car': 'inject_car', '6': 'inject_car'
    }
    
    action = choice_map.get(choice)
    if not action:
        # Re-display menu on invalid choice
        replies = [
            {"title": "1️⃣ Safe Pack 1 (10M/6k)", "payload": "patch_safe_1"},
            {"title": "2️⃣ Safe Pack 2 (6M/1k)", "payload": "patch_safe_2"},
            {"title": "3️⃣ Custom Resources", "payload": "patch_custom"},
            {"title": "4️⃣ Max Nitro Only", "payload": "patch_nitro"},
            {"title": "5️⃣ Map Unlock Only", "payload": "patch_maps"},
            {"title": "6️⃣ Inject Custom Car", "payload": "patch_inject_car"},
            {"title": "⬅️ Back to Menu", "payload": "menu"}
        ]
        await messenger_api.send_quick_replies(sender_psid, "❌ Invalid choice. Please select from the menu:", replies)
        return
        
    # Clean the state dictionary to prevent unpacking duplicate parameters (avoiding TypeError)
    state.pop("state", None)
    state.pop("timestamp", None)

    # ROUTE ACTIONS
    if action == 'custom':
        await messenger_api.send_text(sender_psid, "💰 Enter the exact amount of Silver to add (e.g. 5000000):")
        state_manager.set_user_state(sender_psid, 'awaiting_reseller_custom_silver', **state)
    elif action == 'inject_car':
        await messenger_api.send_text(sender_psid, "🚗 Enter the exact Car ID to inject (e.g. 1045):")
        state_manager.set_user_state(sender_psid, 'awaiting_reseller_car_id', **state)
    else:
        asyncio.create_task(
            execute_reseller_patch_task(
                user_psid=sender_psid,
                email=state['target_email'],
                password=state['target_pass'],
                action=action,
                user_lang=user_lang
            )
        )
        await messenger_api.send_text(sender_psid, "⏳ Launching Patcher Engine... Your request has been queued.")
        state_manager.clear_user_state(sender_psid)

# --- CUSTOM RESOURCE SUB-FLOWS ---

async def handle_reseller_custom_silver(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    try:
        silver = float(text.strip().replace(',', ''))
    except ValueError:
        return await messenger_api.send_text(sender_psid, "❌ Please enter a valid number for Silver:")
        
    state.pop("state", None)
    state.pop("timestamp", None)
    
    await messenger_api.send_text(sender_psid, "✨ Enter the exact amount of Gold to add (e.g. 5000):")
    state_manager.set_user_state(sender_psid, 'awaiting_reseller_custom_gold', silver_val=silver, **state)

async def handle_reseller_custom_gold(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    try:
        gold = int(text.strip().replace(',', ''))
    except ValueError:
        return await messenger_api.send_text(sender_psid, "❌ Please enter a valid integer for Gold:")
        
    state.pop("state", None)
    state.pop("timestamp", None)
    
    await messenger_api.send_text(sender_psid, "📈 Enter the amount of XP to add (e.g. 10000):")
    state_manager.set_user_state(sender_psid, 'awaiting_reseller_custom_xp', silver_val=state['silver_val'], gold_val=gold, **state)

async def handle_reseller_custom_xp(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    try:
        xp = int(text.strip().replace(',', ''))
    except ValueError:
        return await messenger_api.send_text(sender_psid, "❌ Please enter a valid integer for XP:")
        
    asyncio.create_task(
        execute_reseller_patch_task(
            user_psid=sender_psid,
            email=state['target_email'],
            password=state['target_pass'],
            action='custom',
            user_lang=user_lang,
            custom_silver=state['silver_val'],
            custom_gold=state['gold_val'],
            custom_xp=xp
        )
    )
    await messenger_api.send_text(sender_psid, "⏳ Launching Patcher Engine with custom values... Your request has been queued.")
    state_manager.clear_user_state(sender_psid)

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
            target_car_id=car_id
        )
    )
    await messenger_api.send_text(sender_psid, f"⏳ Patcher running... Injecting Car ID {car_id}.")
    state_manager.clear_user_state(sender_psid)

# --- BACKGROUND PATCH EXECUTION ENGINE ---

async def execute_reseller_patch_task(
    user_psid: str, email: str, password: str, action: str, user_lang: str,
    custom_silver: float = 0, custom_gold: int = 0, custom_xp: int = 0, target_car_id: str = ""
):
    try:
        # Generate a secure random Device ID for this session
        dev_id = uuid.uuid4().hex
        
        async with httpx.AsyncClient(http2=True, timeout=60.0) as client:
            client.headers.update({"User-Agent": "UnityPlayer/6000.0.64f1", "X-Project": "STREET"})
            
            # 1. Fetch target account profile
            cont, h = await get_profile_injector(client, email, password, dev_id, carx="", is_target=False)
            profile = decrypt_payload(cont["compressed_data"])
            garage = profile.get("cars", {}).get("items", profile)
            
            summary_actions = []

            # 2. Process Mod Requests
            
            # --- Modification: Ban Safe Pack 1 (10M Silver + 6k Gold) ---
            if action == 'safe_1':
                res = profile.setdefault("resources", {})
                res.setdefault("soft", {"amount": 0})["amount"] = res["soft"].get("amount", 0) + 10000000.0
                res.setdefault("hard", {"amount": 0})["amount"] = res["hard"].get("amount", 0) + 6000
                summary_actions.append("💰 Applied Ban-Safe Pack 1 (+10M Silver, +6k Gold)")

            # --- Modification: Ban Safe Pack 2 (6M Silver + 1k Gold) ---
            elif action == 'safe_2':
                res = profile.setdefault("resources", {})
                res.setdefault("soft", {"amount": 0})["amount"] = res["soft"].get("amount", 0) + 6000000.0
                res.setdefault("hard", {"amount": 0})["amount"] = res["hard"].get("amount", 0) + 1000
                summary_actions.append("💰 Applied Ban-Safe Pack 2 (+6M Silver, +1k Gold)")

            # --- Modification: Custom Input Values ---
            elif action == 'custom':
                res = profile.setdefault("resources", {})
                res.setdefault("soft", {"amount": 0})["amount"] = res["soft"].get("amount", 0) + custom_silver
                res.setdefault("hard", {"amount": 0})["amount"] = res["hard"].get("amount", 0) + custom_gold
                res.setdefault("experience", {"amount": 0})["amount"] = res["experience"].get("amount", 0) + custom_xp
                summary_actions.append(f"💰 Custom Resources added: +{custom_silver:,.0f} Silver, +{custom_gold:,} Gold, +{custom_xp:,} XP")

            # --- Modification: Max Nitro (All cars) ---
            elif action == 'nitro':
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

            # 3. Securely Encrypt and Upload back to CarX Server
            cont["compressed_data"] = encrypt_payload_strict(profile)
            cont["lastSyncTime"] = int(time.time())
            
            r_up = await client.post(f"{BASE_SYNC}/profiles", json=cont, headers=h)
            if r_up.status_code != 200:
                raise Exception(f"Upload rejected by CarX sync server: {r_up.text}")
                
            # 4. Success delivery notification
            success_msg = (
                "🎉 *PATCHING COMPLETED SUCCESSFULLY!* 🎉\n\n"
                f"📧 Account: `{email}`\n"
                "Applied modifications:\n" + "\n".join([f"- {act}" for act in summary_actions]) + "\n\n"
                "Please restart your game completely to view changes! Enjoy! 🔥"
            )
            await messenger_api.send_text(user_psid, success_msg)
            
    except Exception as e:
        print(f"❌ Reseller Patcher Task failed for {user_psid}: {e}")
        fail_msg = (
            "😔 *Patcher Task Failed.*\n\n"
            "An error occurred while connecting or uploading to the CarX servers.\n"
            "Please double check your credentials and try again."
        )
        await messenger_api.send_text(user_psid, fail_msg)
