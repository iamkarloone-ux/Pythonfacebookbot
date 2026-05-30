# admin/operations.py
import asyncio
import database as db
import state_manager
import messenger_api
import carx_cloner
import uuid
import secrets
import math

async def show_admin_menu(sender_psid: str):
    admin_info = await db.get_admin_info()
    online = '✅ Online' if admin_info and admin_info['is_online'] else '❌ Offline'
    maintenance = '🔴 ON' if await db.get_maintenance_status() else '🟢 OFF'
    
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
20: 🔑 Manage Reseller Licenses
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
        target_pass = secrets.token_hex(5)
        
        await messenger_api.send_text(sender_psid, "⏳ Launching Cloner... Please wait up to 30 seconds.")
        
        await carx_cloner.execute_clone(
            src_email=mod['src_email'],
            src_pass=mod['src_pass'],
            src_dev=mod['src_dev_id'],
            src_carx=mod.get('src_carx_id', ''),
            tgt_email=target_email,
            tgt_pass=target_pass
        )
        
        await db.create_account_creation_job(sender_psid, target_email, target_pass, mod_id)
        await messenger_api.send_text(sender_psid, f"✅ Account Done Successfully!\n\n📧: `{target_email}`\n🔐: `{target_pass}`")
        
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Cloner Failed: {e}")

# --- VIEW JOBS ---
async def handle_view_jobs(sender_psid: str):
    jobs = await db.get_creation_jobs()
    if not jobs:
        return await messenger_api.send_text(sender_psid, "No account creation jobs found.")
        
    response = "--- Recent Cloner Jobs ---\n\n"
    for job in jobs:
        emoji = {'pending': '⏳', 'processing': '⚙️', 'completed': '✅', 'failed': '❌', 'delivered': '🎉'}.get(job['status'], '❓')
        response += f"{emoji} Job ID: {job['job_id']}\n"
        response += f"   User: {job['user_psid']}\n"
        response += f"   Status: {job['status']}\n"
        if job['result_message']:
            response += f"   Result: {job['result_message'][:100]}...\n"
        response += "\n"
        
    await messenger_api.send_text(sender_psid, response)

# --- REPLY TO USER ---
async def prompt_reply_psid(sender_psid: str):
    await messenger_api.send_text(sender_psid, "Enter the PSID of the user you want to reply to:")
    state_manager.set_user_state(sender_psid, 'awaiting_reply_psid')

async def prompt_reply_username(sender_psid: str, text: str):
    target = text.strip()
    await messenger_api.send_text(sender_psid, f"✅ Target: {target}. Now enter the USERNAME/EMAIL.")
    state_manager.set_user_state(sender_psid, 'awaiting_reply_username', target_psid=target)

async def prompt_reply_password(sender_psid: str, text: str):
    state = state_manager.get_user_state(sender_psid)
    username = text.strip()
    await messenger_api.send_text(sender_psid, "✅ Now enter the PASSWORD.")
    state_manager.set_user_state(sender_psid, 'awaiting_reply_password', target_psid=state['target_psid'], username=username)

async def process_reply_send(sender_psid: str, text: str):
    state = state_manager.get_user_state(sender_psid)
    password = text.strip()
    
    msg = f"🎉 Here are your account details!\n\n📧 Username: `{state['username']}`\n🔐 Password: `{password}`\n\nThank you for your trust! Enjoy! 💙"
    
    try:
        await messenger_api.send_text(state['target_psid'], msg)
        await messenger_api.send_text(sender_psid, "✅ Message sent to user successfully.")
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Failed to send: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

# --- PAUSE/RESUME USER ---
async def prompt_pause_toggle(sender_psid: str):
    await messenger_api.send_text(sender_psid, "Enter the PSID of the user to pause/resume.")
    state_manager.set_user_state(sender_psid, 'awaiting_pause_toggle_psid')

async def process_pause_toggle(sender_psid: str, text: str):
    target = text.strip()
    is_paused = await db.is_user_paused(target)
    if is_paused:
        await db.resume_user(target)
        await messenger_api.send_text(sender_psid, f"✅ User {target} RESUMED. Bot will now respond.")
    else:
        await db.pause_user(target)
        await messenger_api.send_text(sender_psid, f"✅ User {target} PAUSED. Bot will ignore them.")
    state_manager.clear_user_state(sender_psid)

# --- BROADCAST ---
async def prompt_broadcast(sender_psid: str):
    await messenger_api.send_text(sender_psid, "📢 Type the message you want to broadcast (Type 'Menu' to cancel):")
    state_manager.set_user_state(sender_psid, 'awaiting_broadcast_message')

async def process_broadcast_confirm(sender_psid: str, text: str):
    msg = text.strip()
    count = len(await db.get_all_user_psids())
    await messenger_api.send_text(sender_psid, f"This will send to ~{count} users:\n---\n{msg}\n---\nReply 'CONFIRM' to proceed.")
    state_manager.set_user_state(sender_psid, 'awaiting_broadcast_confirmation', message=msg)

async def process_broadcast_execute(sender_psid: str, text: str):
    if text.strip().upper() != 'CONFIRM':
        state_manager.clear_user_state(sender_psid)
        return await messenger_api.send_text(sender_psid, "❌ Broadcast cancelled.")
        
    state = state_manager.get_user_state(sender_psid)
    msg = state['message']
    state_manager.clear_user_state(sender_psid)
    
    await messenger_api.send_text(sender_psid, "🚀 Starting broadcast. You will be notified when complete.")
    psids = await db.get_all_user_psids()
    
    success, error = 0, 0
    for psid in psids:
        try:
            await messenger_api.send_text(psid, msg)
            success += 1
        except Exception:
            error += 1
        await asyncio.sleep(0.1)
        
    await messenger_api.send_text(sender_psid, f"✅ Broadcast complete!\nSuccess: {success}\nFailed: {error}")

# --- SALES STATS ---
async def prompt_sales_stats(sender_psid: str):
    await messenger_api.send_text(sender_psid, "Choose period:\n1. Daily\n2. Weekly\n3. Monthly")
    state_manager.set_user_state(sender_psid, 'awaiting_sales_stats_period')

async def process_sales_stats(sender_psid: str, text: str):
    period_map = {'1': 'daily', 'daily': 'daily', '2': 'weekly', 'weekly': 'weekly', '3': 'monthly', 'monthly': 'monthly'}
    period = period_map.get(text.strip())
    
    if not period:
        return await messenger_api.send_text(sender_psid, "Invalid choice. Type 1, 2, or 3.")
        
    try:
        stats = await db.get_sales_statistics(period)
        if not stats:
            await messenger_api.send_text(sender_psid, f"No sales data found for the {period} period.")
        else:
            total = 0.0
            response = f"📊 --- {period.capitalize()} Sales Report ---\n\n"
            for stat in stats:
                total += stat['total_revenue']
                response += f"Mod: {stat['name']}\n  - Sales: {stat['sales_count']}\n  - Revenue: ₱{stat['total_revenue']:,.2f}\n\n"
            response += f"--- Total Revenue: ₱{total:,.2f} ---"
            await messenger_api.send_text(sender_psid, response)
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Error: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

# --- EDIT ADMIN INFO ---
async def prompt_edit_admin(sender_psid: str):
    msg = "Provide new admin info.\nFormat: Facebook ID: [New ID], GCash Number: [New Number]"
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_edit_admin')

async def process_edit_admin(sender_psid: str, text: str):
    try:
        parts = [p.strip() for p in text.split(',')]
        new_id = None
        new_gcash = None
        
        for p in parts:
            if p.lower().startswith('facebook id:'):
                new_id = p.split(':')[1].strip()
            elif p.lower().startswith('gcash number:'):
                new_gcash = p.split(':')[1].strip()
                
        if not new_id or not new_gcash:
            raise ValueError("Missing details. Please ensure you include both.")
            
        await db.update_admin_info(new_id, new_gcash)
        await messenger_api.send_text(sender_psid, "✅ Admin info updated successfully.")
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Invalid format. Error: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

# --- RESELLER LICENSE PANEL OPERATIONS ---

async def show_license_submenu(sender_psid: str):
    msg = (
        "🔑 *Reseller License Panel* 🔑\n\n"
        "Reply with:\n"
        "👉 *20a* : ➕ Create License Key\n"
        "👉 *20b* : 👁️ View Licenses & Time Left\n"
        "👉 *20c* : 🗑️ Delete License Key\n\n"
        "Type 'Menu' to exit."
    )
    await messenger_api.send_text(sender_psid, msg)

async def prompt_create_license(sender_psid: str):
    msg = (
        "Provide license details in this exact format:\n"
        "🔑 *[Key], [Days], [User Name], [Tier]*\n\n"
        "Tiers: `free` or `premium` (defaults to premium if left blank).\n\n"
        "Example: `KEY-VIP-99, 30, John Doe, premium`\n"
        "Example: `KEY-FREE-99, 30, Jane Doe, free`"
    )
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_create_license_details')

async def process_create_license(sender_psid: str, text: str):
    try:
        parts = [p.strip() for p in text.split(',')]
        if len(parts) < 3:
            raise ValueError("Input format is incomplete.")
        
        key_input = parts[0]
        days_input = int(parts[1])
        name_input = parts[2]
        tier_input = parts[3].lower() if len(parts) > 3 else 'premium'
        
        if tier_input not in ['free', 'premium']:
            tier_input = 'premium'
        
        await db.add_license_key(key_input, days_input, name_input, tier_input)
        await messenger_api.send_text(
            sender_psid, 
            f"✅ License Key `{key_input}` generated successfully for {name_input} "
            f"({days_input} Days) under [{tier_input.upper()}] tier."
        )
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Format error. Use: Key, Days, Name, Tier. Details: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

async def handle_view_licenses(sender_psid: str):
    licenses = await db.get_all_licenses()
    if not licenses:
        return await messenger_api.send_text(sender_psid, "ℹ️ No license keys found in the database.")
        
    response = "🔑 --- Reseller Licenses List ---\n\n"
    for lic in licenses:
        days_left = math.ceil(lic['days_remaining']) if lic['days_remaining'] > 0 else 0
        status_emoji = "🟢 Active" if (lic['is_active'] and days_left > 0) else "🔴 Expired"
        tier_label = lic.get('tier', 'premium').upper()
        
        response += (
            f"👤 *Reseller:* {lic['assigned_to'] or 'Unknown'}\n"
            f"🔑 *Key:* `{lic['key']}`\n"
            f"🏷️ *Tier:* `{tier_label}`\n"
            f"⏱️ *Remaining:* {days_left} Days ({status_emoji})\n"
            f"📅 *Expires:* {lic['expires_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
        )
        
    await messenger_api.send_text(sender_psid, response)

async def prompt_delete_license(sender_psid: str):
    await messenger_api.send_text(sender_psid, "Enter the exact License Key you want to permanently delete:")
    state_manager.set_user_state(sender_psid, 'awaiting_delete_license_key')

async def process_delete_license(sender_psid: str, text: str):
    key_input = text.strip()
    try:
        deleted = await db.deactivate_license_key(key_input)
        if deleted > 0:
            await messenger_api.send_text(sender_psid, f"✅ License `{key_input}` deleted successfully.")
        else:
            await messenger_api.send_text(sender_psid, f"❌ License `{key_input}` was not found.")
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Database deletion failed: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)
