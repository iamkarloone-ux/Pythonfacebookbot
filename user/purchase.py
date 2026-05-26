import database as db
import state_manager
import messenger_api
import language_manager as lang
import user.manual as manual
import secrets
from user.tasks import process_account_creation
from config import ADMIN_ID

def generate_password(length=10):
    """Generates a secure random password."""
    return secrets.token_hex(length // 2)

async def handle_view_mods(sender_psid: str, user_lang: str = 'en'):
    mods = await db.get_mods()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    if not mods:
        await messenger_api.send_quick_replies(sender_psid, lang.get_text('mods_none_available', user_lang), replies)
        return
        
    response = f"{lang.get_text('mods_header', user_lang)}\n"
    for mod in mods:
        claims_text = '1 Replacement' if mod['default_claims_max'] == 1 else f"{mod['default_claims_max']} Replacements"
        response += f"\n📦 Type {mod['id']}:\n{mod['description'] or 'N/A'}\n💰 Price: {mod['price']} PHP\n🔁 FreeAcc: {claims_text}\n🖼️ Image: {mod['image_url'] or 'N/A'}\n"
        
    final_message = response + f"\n{lang.get_text('mods_purchase_prompt', user_lang)}"
    await messenger_api.send_quick_replies(sender_psid, final_message, replies)
    state_manager.set_user_state(sender_psid, 'awaiting_want_mod', lang=user_lang)

async def handle_want_mod(sender_psid: str, text: str, user_lang: str = 'en'):
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    try:
        mod_id = int(text.strip())
    except ValueError:
        await messenger_api.send_quick_replies(sender_psid, lang.get_text('purchase_invalid_format', user_lang), replies)
        return
        
    mod = await db.get_mod_by_id(mod_id)
    if not mod:
        await messenger_api.send_quick_replies(sender_psid, lang.get_text('purchase_invalid_mod', user_lang), replies)
        return
        
    prompt_email_msg = lang.get_text('purchase_prompt_email', user_lang).replace('{modId}', str(mod['id'])).replace('{modName}', mod['name'])
    await messenger_api.send_quick_replies(sender_psid, prompt_email_msg, replies)
    state_manager.set_user_state(sender_psid, 'awaiting_email_for_purchase', modId=mod['id'], lang=user_lang)

async def handle_email_for_purchase(sender_psid: str, text: str, user_lang: str = 'en'):
    state = state_manager.get_user_state(sender_psid)
    mod_id = state.get('modId')
    email = text.strip()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    if "@" not in email or "." not in email:
        await messenger_api.send_quick_replies(sender_psid, lang.get_text('purchase_invalid_email', user_lang), replies)
        return
        
    mod = await db.get_mod_by_id(mod_id)
    admin_info = await db.get_admin_info()
    gcash_number = admin_info.get('gcash_number') if admin_info else "09123963204"
    
    payment_message = lang.get_text('purchase_prompt_payment', user_lang)\
        .replace('{price}', str(mod['price']))\
        .replace('{gcashNumber}', gcash_number)
        
    await messenger_api.send_quick_replies(sender_psid, payment_message, replies)
    state_manager.set_user_state(sender_psid, 'awaiting_receipt_for_purchase', modId=mod_id, email=email, lang=user_lang)

async def handle_receipt_analysis(sender_psid: str, analysis: dict, ADMIN_ID: str, user_lang: str = 'en'):
    state = state_manager.get_user_state(sender_psid) or {}
    image_url = state.get('image_url', '') # Safe extraction of URL
    
    amount_str = str(analysis.get("extracted_info", {}).get("amount", "")).replace(',', '')
    ref_number = str(analysis.get("extracted_info", {}).get("reference_number", "")).strip()
    
    try:
        amount = float(amount_str)
    except ValueError:
        amount = 0.0

    user_name = 'A User'
    try:
        user_name = await messenger_api.get_user_profile(sender_psid)
    except Exception as e:
        print(f"Profile Fetch Failed: {e}")

    # PURE PYTHON AI FAILURE CHECK: Redirects cleanly to Manual Entry
    if amount == 0.0 or not ref_number or len(ref_number) != 13 or not ref_number.isdigit():
        print(f"[AI-SCAN-FAILED] Redirecting user {sender_psid} to manual entry.")
        await manual.start_manual_entry_flow(sender_psid, image_url, user_lang)
        return

    matching_mods = await db.get_mods_by_price(amount)
    if len(matching_mods) == 1:
        mod = matching_mods[0]
        confirmation_msg = lang.get_text('receipt_confirm_purchase', user_lang)\
            .replace('{amount}', str(amount)).replace('{modId}', str(mod['id'])).replace('{modName}', mod['name'])
            
        replies = [
            {"title": lang.get_text('confirm_yes', user_lang), "payload": "confirm_yes"}, 
            {"title": lang.get_text('confirm_no', user_lang), "payload": "confirm_no"}
        ]
        
        await messenger_api.send_quick_replies(sender_psid, confirmation_msg, replies)
        state_manager.set_user_state(sender_psid, 'awaiting_mod_confirmation', 
                                     refNumber=ref_number, 
                                     modId=mod['id'], 
                                     modName=mod['name'], 
                                     email=state.get('email'), 
                                     lang=user_lang)

    elif len(matching_mods) > 1:
        mod_list = ''
        for m in matching_mods: 
            mod_list += f"- Mod {m['id']}: {m['name']}\n"
        clarification_msg = lang.get_text('receipt_clarify_purchase', user_lang).replace('{amount}', str(amount)).replace('{modList}', mod_list)
        await messenger_api.send_text(sender_psid, clarification_msg)
        
        state_manager.set_user_state(sender_psid, 'awaiting_mod_clarification', 
                                     refNumber=ref_number, 
                                     email=state.get('email'), 
                                     lang=user_lang)
    else:
        await messenger_api.send_text(sender_psid, lang.get_text('receipt_no_match', user_lang).replace('{amount}', str(amount)))
        await messenger_api.send_text(ADMIN_ID, f"User {user_name} paid {amount} PHP, but no mod matches. Ref: {ref_number}")
        state_manager.set_user_state(sender_psid, 'language_set', lang=user_lang)

async def handle_mod_confirmation(sender_psid: str, text: str, ADMIN_ID: str, user_lang: str = 'en'):
    state = state_manager.get_user_state(sender_psid)
    positive_confirmation = lang.get_text('confirm_yes', user_lang).lower()
    
    if text.lower() in ['confirm_yes', 'yes', positive_confirmation]:
        try:
            user_name = 'A User'
            try: user_name = await messenger_api.get_user_profile(sender_psid)
            except Exception: pass

            await db.add_reference(state['refNumber'], sender_psid, state['modId'])
            
            password = generate_password()
            safe_email = state.get('email') or "No Email Provided" 

            # Run cloner in the background
            import asyncio
            mod = await db.get_mod_by_id(state['modId'])
            asyncio.create_task(process_account_creation(sender_psid, mod, safe_email, user_lang))
            
            await messenger_api.send_text(ADMIN_ID, f"🤖 Automation job queued for {user_name}\nMod: {state['modName']}\nRef: {state['refNumber']}")

        except Exception as e:
            if 'Duplicate' in str(e):
                await messenger_api.send_text(sender_psid, lang.get_text('error_duplicate_ref', user_lang))
            else: 
                print(f"Critical Purchase Error: {e}")
                await messenger_api.send_text(sender_psid, lang.get_text('error_unexpected_user', user_lang))
    else:
        await messenger_api.send_text(sender_psid, lang.get_text('receipt_transaction_cancelled', user_lang))
    
    state_manager.clear_user_state(sender_psid)
    state_manager.set_user_state(sender_psid, 'language_set', lang=user_lang)

async def handle_mod_clarification(sender_psid: str, text: str, ADMIN_ID: str, user_lang: str = 'en'):
    state = state_manager.get_user_state(sender_psid)
    try:
        mod_id = int(text.strip())
        mod = await db.get_mod_by_id(mod_id)
        if not mod:
            await messenger_api.send_text(sender_psid, lang.get_text('manual_entry_invalid_mod', user_lang))
            return 
    except ValueError:
        await messenger_api.send_text(sender_psid, lang.get_text('manual_entry_invalid_mod', user_lang))
        return

    try:
        user_name = 'A User'
        try: user_name = await messenger_api.get_user_profile(sender_psid)
        except Exception: pass

        await db.add_reference(state['refNumber'], sender_psid, mod_id)
        
        safe_email = state.get('email') or "No Email Provided"

        # Run cloner in the background
        import asyncio
        asyncio.create_task(process_account_creation(sender_psid, mod, safe_email, user_lang))
        
        await messenger_api.send_text(ADMIN_ID, f"🤖 Automation job queued for {user_name}\nMod: {mod['name']}\nRef: {state['refNumber']}")

    except Exception as e:
        if 'Duplicate' in str(e):
            await messenger_api.send_text(sender_psid, lang.get_text('error_duplicate_ref', user_lang))
        else: 
            await messenger_api.send_text(sender_psid, lang.get_text('error_unexpected_user', user_lang))
    
    state_manager.clear_user_state(sender_psid)
    state_manager.set_user_state(sender_psid, 'language_set', lang=user_lang)
