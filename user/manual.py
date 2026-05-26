import state_manager
import messenger_api
import database as db
import language_manager as lang

async def start_manual_entry_flow(sender_psid: str, image_url: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid) or {}
    email = state.get('email')
    
    msg = lang.get_text('manual_entry_start', user_lang)
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_manual_ref', email=email, lang=user_lang)

async def handle_manual_reference(sender_psid: str, text: str, user_lang: str):
    ref_number = text.strip()
    if len(ref_number) != 13 or not ref_number.isdigit():
        return await messenger_api.send_text(sender_psid, lang.get_text('manual_entry_invalid_ref', user_lang))
        
    state = state_manager.get_user_state(sender_psid)
    mods = await db.get_mods()
    
    msg = lang.get_text('manual_entry_thanks', user_lang) + "\n\n"
    for m in mods:
        msg += f"- Mod {m['id']}: {m['name']}\n"
    msg += "\n" + lang.get_text('manual_entry_prompt_mod', user_lang)
    
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_manual_mod', refNumber=ref_number, email=state.get('email'), lang=user_lang)

# (The logic to process the Mod choice here is identical to `handle_mod_confirmation` in purchase.py)
