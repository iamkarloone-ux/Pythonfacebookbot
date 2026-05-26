import asyncio
import secrets
import traceback
import carx_cloner
import database as db
import messenger_api
import language_manager as lang
from config import ADMIN_ID

async def process_account_creation(user_psid: str, mod_data: dict, target_email: str, user_lang: str):
    try:
        target_password = secrets.token_hex(5)
        await messenger_api.send_text(user_psid, lang.get_text('automation_started_user', user_lang).replace('{modName}', mod_data['name']))
        
        # DETECT SOURCE TYPE
        if mod_data["src_email"] and mod_data["src_email"].startswith("http"):
            print(f"[Cloner] Using Static Snapshot from: {mod_data['src_email']}")
            await carx_cloner.execute_clone_from_snapshot(
                profile_url=mod_data["src_email"],
                tgt_email=target_email,
                tgt_pass=target_password
            )
        else:
            print("[Cloner] Using Dynamic Live Fetching")
            await carx_cloner.execute_clone(
                src_email=mod_data['src_email'],
                src_pass=mod_data['src_pass'],
                src_dev=mod_data['src_dev_id'],
                src_carx=mod_data.get('src_carx_id', ''),
                tgt_email=target_email,
                tgt_pass=target_password
            )
        
        await db.create_account_creation_job(user_psid, target_email, target_password, mod_data['id'], user_lang)
        
        success_msg = lang.get_text('delivery_success', user_lang)
        success_msg += f"\n\n📧 Username: `{target_email}`\n🔐 Password: `{target_password}`\n\nThank you for your trust! Enjoy! 💙"
        await messenger_api.send_text(user_psid, success_msg)
        
    except Exception as e:
        print(f"Failed to clone for {user_psid}: {e}")
        traceback.print_exc()
        fail_msg = lang.get_text('delivery_failed_user', user_lang)
        await messenger_api.send_text(user_psid, fail_msg)
        
        admin_msg = f"🚨 AUTOMATION FAILED 🚨\nUser: {user_psid}\nMod: {mod_data['name']}\nEmail: {target_email}\nError: {e}"
        await messenger_api.send_text(ADMIN_ID, admin_msg)
