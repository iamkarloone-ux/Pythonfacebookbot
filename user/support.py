import database as db
import state_manager
import messenger_api
import language_manager as lang
from config import ADMIN_ID

async def handle_view_proofs(sender_psid: str, user_lang: str):
    msg = lang.get_text('proofs_message', user_lang)
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    await messenger_api.send_quick_replies(sender_psid, msg, replies)

# --- CONTACT ADMIN ---
async def prompt_admin_message(sender_psid: str, user_lang: str):
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    await messenger_api.send_quick_replies(sender_psid, lang.get_text('contact_admin_prompt', user_lang), replies)
    state_manager.set_user_state(sender_psid, 'awaiting_admin_message', lang=user_lang)

async def forward_message_to_admin(sender_psid: str, text: str, user_lang: str):
    user_name = await messenger_api.get_user_profile(sender_psid)
    forward_msg = f"📩 Message from {user_name} ({sender_psid}):\n\n\"{text}\"\n\nTo reply, use the Admin Menu (Type 10)."
    
    await messenger_api.send_text(ADMIN_ID, forward_msg)
    await messenger_api.send_text(sender_psid, lang.get_text('contact_admin_success', user_lang))
    state_manager.clear_user_state(sender_psid)

# --- REPORT ISSUE ---
async def prompt_report_ref(sender_psid: str, user_lang: str):
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    await messenger_api.send_quick_replies(sender_psid, lang.get_text('report_prompt_ref', user_lang), replies)
    state_manager.set_user_state(sender_psid, 'awaiting_report_ref', lang=user_lang)

async def process_report_ref(sender_psid: str, text: str, user_lang: str):
    ref_number = text.strip()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    if len(ref_number) != 13 or not ref_number.isdigit():
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('claims_check_invalid_format', user_lang), replies)
        
    ref = await db.get_reference(ref_number)
    if not ref:
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('report_not_found', user_lang), replies)
        
    await messenger_api.send_quick_replies(sender_psid, lang.get_text('report_prompt_issue', user_lang), replies)
    state_manager.set_user_state(sender_psid, 'awaiting_report_issue_desc', refNumber=ref_number, lang=user_lang)

async def process_report_description(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    issue = text.strip()
    user_name = await messenger_api.get_user_profile(sender_psid)
    
    admin_notification = f"🚨 NEW ACCOUNT ISSUE REPORT 🚨\n\nUser: {user_name} ({sender_psid})\nReference: {state['refNumber']}\n\nIssue:\n\"{issue}\""
    await messenger_api.send_text(ADMIN_ID, admin_notification)
    
    await messenger_api.send_text(sender_psid, lang.get_text('report_success_user', user_lang))
    state_manager.clear_user_state(sender_psid)
