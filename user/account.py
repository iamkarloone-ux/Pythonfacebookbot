import time
import asyncio
import database as db
import state_manager
import messenger_api
import language_manager as lang
from user.tasks import process_account_creation

async def prompt_check_claims(sender_psid: str, user_lang: str):
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    await messenger_api.send_quick_replies(sender_psid, lang.get_text('claims_check_prompt', user_lang), replies)
    state_manager.set_user_state(sender_psid, 'awaiting_ref_for_check', lang=user_lang)

async def process_check_claims(sender_psid: str, ref_number: str, user_lang: str):
    ref_number = ref_number.strip()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    if len(ref_number) != 13 or not ref_number.isdigit():
        msg = lang.get_text('claims_check_invalid_format', user_lang)
    else:
        ref = await db.get_reference(ref_number)
        if not ref:
            msg = lang.get_text('claims_check_not_found', user_lang)
        else:
            remaining = ref['claims_max'] - ref['claims_used']
            claims_text = "1 replacement account" if remaining == 1 else f"{remaining} replacement accounts"
            msg = lang.get_text('claims_check_result', user_lang).replace('{claimsText}', claims_text).replace('{modId}', str(ref['mod_id'])).replace('{modName}', ref['mod_name'])
            
    state_manager.clear_user_state(sender_psid)
    await messenger_api.send_quick_replies(sender_psid, msg, replies)

async def prompt_replacement(sender_psid: str, user_lang: str):
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    await messenger_api.send_quick_replies(sender_psid, lang.get_text('replace_prompt', user_lang), replies)
    state_manager.set_user_state(sender_psid, 'awaiting_ref_for_replacement', lang=user_lang)

async def process_replacement_request(sender_psid: str, ref_number: str, user_lang: str):
    ref_number = ref_number.strip()
    replies = [{"title": "⬅️ Back to Menu", "payload": "menu"}]
    
    if len(ref_number) != 13 or not ref_number.isdigit():
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('claims_check_invalid_format', user_lang), replies)
        
    ref = await db.get_reference(ref_number)
    if not ref:
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('claims_check_not_found', user_lang), replies)
        
    # Check 24-hour cooldown
    if ref.get('last_replacement_timestamp'):
        # PostgreSQL TIMESTAMPTZ to timestamp
        last_time = ref['last_replacement_timestamp'].timestamp()
        if time.time() - last_time < 86400: # 24 hours in seconds
            return await messenger_api.send_quick_replies(sender_psid, lang.get_text('replace_limit_reached', user_lang), replies)
            
    if ref['claims_used'] >= ref['claims_max']:
        return await messenger_api.send_quick_replies(sender_psid, lang.get_text('replace_no_claims', user_lang), replies)
        
    # Validation Passed! Start Automation
    state_manager.clear_user_state(sender_psid)
    await db.use_claim(ref['ref_number'])
    
    mod = await db.get_mod_by_id(ref['mod_id'])
    target_email = f"acct-{sender_psid}-{int(time.time())}@replacement.bot"
    
    # Run cloner in background
    asyncio.create_task(process_account_creation(sender_psid, mod, target_email, user_lang))
