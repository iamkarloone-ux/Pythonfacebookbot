import asyncio
import database as db
import state_manager
import messenger_api
import language_manager as lang
import user.manual as manual
from user.tasks import process_account_creation
from config import ADMIN_ID

async def handle_view_mods(sender_psid: str, user_lang: str):
    mods = await db.get_mods()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    if not mods:
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('mods_none_available', user_lang), replies)
        
    msg = f"{lang.get_text('mods_header', user_lang)}\n"
    for m in mods:
        claims_text = "1 Replacement" if m['default_claims_max'] == 1 else f"{m['default_claims_max']} Replacements"
        msg += f"\n📦 Type {m['id']}:\n{m['description'] or 'N/A'}\n💰 Price: {m['price']} PHP\n🔁 FreeAcc: {claims_text}\n🖼️ Image: {m['image_url'] or 'N/A'}\n"
        
    msg += f"\n{lang.get_text('mods_purchase_prompt', user_lang)}"
    await messenger_api.send_quick_replies(sender_psid, msg, replies)
    state_manager.set_user_state(sender_psid, 'awaiting_want_mod', lang=user_lang)

async def handle_want_mod(sender_psid: str, text: str, user_lang: str):
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    try:
        mod_id = int(text.strip())
        mod = await db.get_mod_by_id(mod_id)
        if not mod: raise ValueError()
    except ValueError:
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('purchase_invalid_mod', user_lang), replies)
        
    msg = lang.get_text('purchase_prompt_email', user_lang).replace('{modId}', str(mod['id'])).replace('{modName}', mod['name'])
    await messenger_api.send_quick_replies(sender_psid, msg, replies)
    state_manager.set_user_state(sender_psid, 'awaiting_email_for_purchase', modId=mod['id'], lang=user_lang)

async def handle_email_for_purchase(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    email = text.strip()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    if "@" not in email or "." not in email:
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('purchase_invalid_email', user_lang), replies)
        
    mod = await db.get_mod_by_id(state['modId'])
    admin = await db.get_admin_info()
    gcash = admin.get('gcash_number') if admin else "09123963204"
    
    msg = lang.get_text('purchase_prompt_payment', user_lang).replace('{price}', str(mod['price'])).replace('{gcashNumber}', gcash)
    await messenger_api.send_quick_replies(sender_psid, msg, replies)
    state_manager.set_user_state(sender_psid, 'awaiting_receipt_for_purchase', modId=mod['id'], email=email, lang=user_lang)

async def handle_receipt_analysis(sender_psid: str, analysis: dict, user_lang: str, image_url: str):
    state = state_manager.get_user_state(sender_psid) or {}
    
    amount_str = str(analysis.get("extracted_info", {}).get("amount", ""))
    ref_number = str(analysis.get("extracted_info", {}).get("reference_number", "")).strip()
    
    try:
        amount = float(amount_str)
    except ValueError:
        amount = 0.0

    # IF AI FAILS -> Redirect to manual reference entry
    if amount == 0.0 or not ref_number or len(ref_number) != 13:
        print(f"[AI-SCAN-FAILED] User {sender_psid} to manual entry.")
        return await manual.start_manual_entry_flow(sender_psid, image_url, user_lang)
        
    matching_mods = await db.get_mods_by_price(amount)
    
    if len(matching_mods) == 1:
        mod = matching_mods[0]
        msg = lang.get_text('receipt_confirm_purchase', user_lang).replace('{amount}', str(amount)).replace('{modId}', str(mod['id'])).replace('{modName}', mod['name'])
        replies = [
            {"title": lang.get_text('confirm_yes', user_lang), "payload": "confirm_yes"},
            {"title": lang.get_text('confirm_no', user_lang), "payload": "confirm_no"}
        ]
        await messenger_api.send_quick_replies(sender_psid, msg, replies)
        state_manager.set_user_state(sender_psid, 'awaiting_mod_confirmation', refNumber=ref_number, modId=mod['id'], modName=mod['name'], email=state.get('email'), lang=user_lang)
        
    else:
        # Failsafe if price matches multiple or none
        await manual.start_manual_entry_flow(sender_psid, image_url, user_lang)

async def handle_mod_confirmation(sender_psid: str, lower_text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    confirm_word = lang.get_text('confirm_yes', user_lang).lower()
    
    if lower_text in ['confirm_yes', 'yes', confirm_word]:
        try:
            await db.add_reference(state['refNumber'], sender_psid, state['modId'])
            mod = await db.get_mod_by_id(state['modId'])
            email = state.get('email') or "NoEmailProvided@bot"
            
            # Start Background Cloner
            asyncio.create_task(process_account_creation(sender_psid, mod, email, user_lang))
            
            # Alert Admin
            user_name = await messenger_api.get_user_profile(sender_psid)
            await messenger_api.send_text(ADMIN_ID, f"💰 Purchase Confirmed!\nUser: {user_name}\nMod: {state['modName']}\nRef: {state['refNumber']}")
            
        except Exception as e:
            if "Duplicate" in str(e):
                await messenger_api.send_text(sender_psid, lang.get_text('error_duplicate_ref', user_lang))
            else:
                await messenger_api.send_text(sender_psid, lang.get_text('error_unexpected_user', user_lang))
    else:
        await messenger_api.send_text(sender_psid, lang.get_text('receipt_transaction_cancelled', user_lang))
        
    state_manager.clear_user_state(sender_psid)
