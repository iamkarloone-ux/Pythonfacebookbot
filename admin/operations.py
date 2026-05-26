import asyncio
import database as db
import state_manager
import messenger_api
import carx_cloner
import uuid
import secrets

async def show_admin_menu(sender_psid: str):
    admin_info = await db.get_admin_info()
    online = '✅ Online' if admin_info and admin_info['is_online'] else '❌ Offline'
    maintenance = '🔴 ON' if await db.get_maintenance_status() else '🟢 OFF'
    
    # Note: Removed outdated "Bulk Account" and "Delete Account" types
    menu = f"""Admin Menu:
1: 👁️ View references
3: 🖱️ Edit mod details (Set Cloner Source here)
4: ➕ Add a reference
6: 🖱️ Edit reference Mod
7: ➕ Add a new mod
8: 🗑️ Delete reference
9: Toggle Online Status ({online})
10: 💬 Reply to user
11: 🤖 View clone jobs
12: ⚡ Instant Create Account (Admin Cloner)
13: ➕ Add bulk references
14: ⏸️ Pause/Resume user
15: 🔧 Maintenance Mode ({maintenance})
17: 📢 Broadcast message
18: ✍️ Edit ref claims
19: 📊 View Sales Stats
"""
    await messenger_api.send_text(sender_psid, menu)

async def toggle_admin_status(sender_psid: str):
    info = await db.get_admin_info()
    new_status = not info['is_online']
    await db.set_admin_online_status(new_status)
    await messenger_api.send_text(sender_psid, f"Status updated to: {'✅ Online' if new_status else '❌ Offline'}")

async def toggle_maintenance(sender_psid: str):
    current = await db.get_maintenance_status()
    await db.set_maintenance_status(not current)
    await messenger_api.send_text(sender_psid, f"Maintenance is now {'🟢 OFF' if current else '🔴 ON'}")

# --- ADMIN CREATE ACCOUNT (USING CLONER) ---
async def prompt_admin_create_email(sender_psid: str):
    await messenger_api.send_text(sender_psid, "Enter the target EMAIL address for the new account:")
    state_manager.set_user_state(sender_psid, 'awaiting_admin_create_email')

async def prompt_admin_create_mod(sender_psid: str, text: str):
    email = text.strip()
    mods = await db.get_mods()
    msg = f"Target: {email}\n\nWhich Mod to clone? Reply with Mod ID:\n"
    msg += "\n".join([f"- {m['id']}: {m['name']}" for m in mods])
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_admin_create_mod_id', email=email)

async def process_admin_create(sender_psid: str, text: str):
    state = state_manager.get_user_state(sender_psid)
    state_manager.clear_user_state(sender_psid)
    
    try:
        mod_id = int(text.strip())
        mod = await db.get_mod_by_id(mod_id)
        
        if not mod.get('src_email') or not mod.get('src_dev_id'):
            await messenger_api.send_text(sender_psid, f"❌ Mod {mod_id} cannot be cloned because Source Data (src_email, src_dev_id) is missing. Edit the mod first.")
            return

        target_email = state['email']
        target_pass = secrets.token_hex(5) # 10 char random pass
        
        await messenger_api.send_text(sender_psid, "⏳ Launching Cloner... Please wait up to 30 seconds.")
        
        # We run the cloner synchronously in this async function to ensure we catch errors immediately
        await carx_cloner.execute_clone(
            src_email=mod['src_email'],
            src_pass=mod['src_pass'],
            src_dev=mod['src_dev_id'],
            src_carx=mod.get('src_carx_id', ''),
            tgt_email=target_email,
            tgt_pass=target_pass
        )
        
        await db.create_account_creation_job(sender_psid, target_email, target_pass, mod_id)
        await messenger_api.send_text(sender_psid, f"✅ Account Cloned Successfully!\n\n📧: `{target_email}`\n🔐: `{target_pass}`")
        
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Cloner Failed: {e}")

# (The rest of the standard utility functions like Broadcast, Reply to User, View Jobs, etc. go here)
# ... I will provide `ref_manager.py` and the remaining operations next if you confirm this structure works!
