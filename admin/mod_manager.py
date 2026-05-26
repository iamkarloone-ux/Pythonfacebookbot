import database as db
import state_manager
import messenger_api

async def prompt_add_mod(sender_psid: str):
    msg = "Provide the new mod details.\nFormat: ID, Name, Description, Price, ImageURL, MaxClaims\n\nExample: 1, VIP Mod, Unlocks features, 250, http://image.link/vip.png, 3"
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_add_mod')

async def process_add_mod(sender_psid: str, text: str):
    try:
        parts = [p.strip() for p in text.split(',')]
        mod_id = int(parts[0])
        name = parts[1]
        desc = parts[2]
        price = float(parts[3])
        img = parts[4]
        claims = int(parts[5])
        
        await db.add_mod(mod_id, name, desc, price, img, claims)
        claims_text = f"{claims} default claims"
        await messenger_api.send_text(sender_psid, f"✅ Mod {mod_id} ({name}) created successfully with {claims_text}! \n\n⚠️ IMPORTANT: You still need to Edit this mod (Type 3) to add the Source Account data for the auto-cloner.")
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Could not create mod. Format might be wrong. Error: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

async def prompt_edit_mod(sender_psid: str):
    mods = await db.get_mods()
    if not mods:
        await messenger_api.send_text(sender_psid, "❌ There are no mods to edit. Add one first.")
        return state_manager.clear_user_state(sender_psid)
        
    msg = "Available Mod IDs:\n" + "\n".join([f"- ID: {m['id']}, Name: {m['name']}" for m in mods])
    msg += "\nWhich mod would you like to edit? Type the ID."
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_edit_mod_id')

async def process_edit_mod_detail(sender_psid: str, text: str):
    try:
        mod_id = int(text.strip())
        mod = await db.get_mod_by_id(mod_id)
        if not mod:
            raise ValueError()
            
        msg = f"Editing Mod {mod['id']} ({mod['name']}).\n\nCurrent Details:\n"
        msg += f"- Name: {mod['name']}\n- Price: {mod['price']}\n- Max Claims: {mod['default_claims_max']}\n"
        msg += f"- Src Email: {mod.get('src_email', 'Not Set')}\n- Src Pass: {mod.get('src_pass', 'Not Set')}\n"
        msg += f"- Src Dev ID: {mod.get('src_dev_id', 'Not Set')}\n- Src CarX ID: {mod.get('src_carx_id', 'Not Set')}\n\n"
        msg += "What to change? Reply with: 'name', 'price', 'claims', 'src_email', 'src_pass', 'src_dev', or 'src_carx'."
        
        await messenger_api.send_text(sender_psid, msg)
        state_manager.set_user_state(sender_psid, 'awaiting_edit_mod_detail_choice', modId=mod_id)
    except ValueError:
        await messenger_api.send_text(sender_psid, "Invalid Mod ID. Type 'Menu' to cancel.")

async def process_edit_mod_value(sender_psid: str, choice: str):
    valid_choices = ['name', 'description', 'price', 'image', 'claims', 'src_email', 'src_pass', 'src_dev', 'src_carx']
    if choice not in valid_choices:
        await messenger_api.send_text(sender_psid, f"Invalid choice. Valid: {', '.join(valid_choices)}")
        return
        
    state = state_manager.get_user_state(sender_psid)
    await messenger_api.send_text(sender_psid, f"What is the new {choice} for Mod {state['modId']}?")
    state_manager.set_user_state(sender_psid, 'awaiting_edit_mod_new_value', modId=state['modId'], detail=choice)

async def process_edit_mod_save(sender_psid: str, text: str):
    state = state_manager.get_user_state(sender_psid)
    mod_id = state['modId']
    detail = state['detail']
    
    # Map friendly names to DB columns
    field_map = {
        'image': 'image_url', 'claims': 'default_claims_max', 'src_dev': 'src_dev_id', 'src_carx': 'src_carx_id'
    }
    db_field = field_map.get(detail, detail)
    
    val = text.strip()
    try:
        if detail in ['price']: val = float(val)
        if detail in ['claims']: val = int(val)
            
        await db.update_mod_details(mod_id, {db_field: val})
        await messenger_api.send_text(sender_psid, f"✅ {detail} updated.\n\nEdit another detail? (Yes / No)")
        state_manager.set_user_state(sender_psid, 'awaiting_edit_mod_continue', modId=mod_id)
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Error: {e}")
        state_manager.clear_user_state(sender_psid)

async def process_edit_mod_continue(sender_psid: str, text: str):
    if text == 'yes':
        state = state_manager.get_user_state(sender_psid)
        await messenger_api.send_text(sender_psid, "Reply with 'name', 'price', 'claims', 'src_email', 'src_pass', 'src_dev', or 'src_carx'.")
        state_manager.set_user_state(sender_psid, 'awaiting_edit_mod_detail_choice', modId=state['modId'])
    else:
        state_manager.clear_user_state(sender_psid)
        await messenger_api.send_text(sender_psid, "Finished editing. Type 'Menu' to return.")
