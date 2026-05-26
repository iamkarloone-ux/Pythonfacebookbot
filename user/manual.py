import asyncio
import database as db
import state_manager
import messenger_api
import language_manager as lang
from user.tasks import process_account_creation
from config import ADMIN_ID

async def start_manual_entry_flow(sender_psid: str, image_url: str, user_lang: str):
    """
    Triggered when the AI scanner fails to extract the amount or reference number.
    Prompts the user to type their reference number manually.
    """
    state = state_manager.get_user_state(sender_psid) or {}
    email = state.get('email')
    
    msg = lang.get_text('manual_entry_start', user_lang)
    await messenger_api.send_text(sender_psid, msg)
    
    # Transition to manual reference state
    state_manager.set_user_state(
        sender_psid, 
        'awaiting_manual_ref', 
        email=email, 
        lang=user_lang, 
        image_url=image_url
    )

async def handle_manual_reference(sender_psid: str, text: str, user_lang: str):
    """
    Validates the manually entered 13-digit reference number, then asks which Mod they bought.
    """
    ref_number = text.strip()
    
    # Check if it's exactly 13 digits
    if len(ref_number) != 13 or not ref_number.isdigit():
        return await messenger_api.send_text(sender_psid, lang.get_text('manual_entry_invalid_ref', user_lang))
        
    state = state_manager.get_user_state(sender_psid)
    mods = await db.get_mods()
    
    # Build a list of available mods to show the user
    msg = lang.get_text('manual_entry_thanks', user_lang) + "\n\n"
    for m in mods:
        msg += f"- Mod {m['id']}: {m['name']}\n"
    msg += "\n" + lang.get_text('manual_entry_prompt_mod', user_lang)
    
    await messenger_api.send_text(sender_psid, msg)
    
    # Transition to manual mod selection state
    state_manager.set_user_state(
        sender_psid, 
        'awaiting_manual_mod', 
        refNumber=ref_number, 
        email=state.get('email'), 
        lang=user_lang
    )

async def handle_manual_mod_selection(sender_psid: str, text: str, user_lang: str):
    """
    Validates the Mod selection, saves the purchase to the database,
    and triggers the background Auto-Cloner.
    """
    state = state_manager.get_user_state(sender_psid)
    
    try:
        mod_id = int(text.strip())
        mod = await db.get_mod_by_id(mod_id)
        if not mod: 
            raise ValueError()
    except ValueError:
        return await messenger_api.send_text(sender_psid, lang.get_text('manual_entry_invalid_mod', user_lang))
        
    try:
        # 1. Add Reference to Database
        await db.add_reference(state['refNumber'], sender_psid, mod['id'])
        
        email = state.get('email') or f"manual-{sender_psid}@bot.com"
        
        # 2. Start Background Auto-Cloner Task
        asyncio.create_task(process_account_creation(sender_psid, mod, email, user_lang))
        
        # 3. Alert the Admin of the manual purchase
        user_name = await messenger_api.get_user_profile(sender_psid)
        admin_msg = f"💰 Manual Purchase Confirmed!\nUser: {user_name}\nMod: {mod['name']}\nRef: {state['refNumber']}"
        await messenger_api.send_text(ADMIN_ID, admin_msg)
        
    except Exception as e:
        if "Duplicate" in str(e):
            await messenger_api.send_text(sender_psid, lang.get_text('error_duplicate_ref', user_lang))
        else:
            print(f"Error in manual mod selection for {sender_psid}: {e}")
            await messenger_api.send_text(sender_psid, lang.get_text('error_unexpected_user', user_lang))
            
    finally:
        # Always clear state so the user can use the menu normally again
        state_manager.clear_user_state(sender_psid)
