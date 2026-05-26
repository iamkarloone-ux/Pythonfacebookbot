import database as db
import state_manager
import messenger_api
import math

REFERENCES_PER_PAGE = 10

async def handle_view_references(sender_psid: str, page: int = 1):
    all_refs = await db.get_all_references()
    if not all_refs:
        state_manager.clear_user_state(sender_psid)
        return await messenger_api.send_text(sender_psid, "No reference numbers have been submitted yet.\nType 'Menu' to return.")
        
    total_pages = math.ceil(len(all_refs) / REFERENCES_PER_PAGE)
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * REFERENCES_PER_PAGE
    end_idx = start_idx + REFERENCES_PER_PAGE
    refs_to_show = all_refs[start_idx:end_idx]
    
    response = f"--- Reference Numbers (Page {page}/{total_pages}) ---\n\n"
    for r in refs_to_show:
        response += f"Ref: {r['ref_number']}\nMod: {r['mod_name']}\nUser: {r['user_id']}\nClaims: {r['claims_used']}/{r['claims_max']}\n\n"
        
    response += "--- Options ---\n"
    if page < total_pages: response += "Type '1' for Next Page\n"
    if page > 1: response += "Type '2' for Previous Page\n"
    response += "Type 'Menu' to return."
    
    await messenger_api.send_text(sender_psid, response)
    state_manager.set_user_state(sender_psid, 'viewing_references', page=page)

# --- ADD REFERENCE ---
async def prompt_add_ref(sender_psid: str):
    await messenger_api.send_text(sender_psid, "Please provide the 13-digit GCash reference number you want to add.")
    state_manager.set_user_state(sender_psid, 'awaiting_add_ref_number')

async def process_add_ref_mod(sender_psid: str, text: str):
    ref_number = text.strip()
    if len(ref_number) != 13 or not ref_number.isdigit():
        return await messenger_api.send_text(sender_psid, "Invalid reference number format. Must be 13 digits.")
        
    mods = await db.get_mods()
    if not mods:
        state_manager.clear_user_state(sender_psid)
        return await messenger_api.send_text(sender_psid, "❌ No mods in system. Add a mod first.")
        
    msg = "Reference number accepted. Choose the mod:\n\n"
    msg += "\n".join([f"- ID: {m['id']}, Name: {m['name']}" for m in mods])
    
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_add_ref_mod_id', ref_number=ref_number)

async def process_add_ref_save(sender_psid: str, text: str):
    state = state_manager.get_user_state(sender_psid)
    try:
        mod_id = int(text.strip())
        claims_added = await db.add_reference(state['ref_number'], 'ADMIN_ADDED', mod_id)
        await messenger_api.send_text(sender_psid, f"✅ Reference {state['ref_number']} added to Mod {mod_id} with {claims_added} claims.")
    except Exception as e:
        if "Duplicate" in str(e):
            await messenger_api.send_text(sender_psid, "Could not add reference. It already exists.")
        else:
            await messenger_api.send_text(sender_psid, f"Error: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

# --- EDIT/DELETE REFERENCE ---
async def prompt_edit_ref(sender_psid: str):
    await messenger_api.send_text(sender_psid, "Provide the ref number and the new mod ID.\nFormat: [ref_number], Mod [ID]\nExample: 1234567890123, Mod 2")
    state_manager.set_user_state(sender_psid, 'awaiting_edit_ref')

async def process_edit_ref(sender_psid: str, text: str):
    try:
        parts = [p.strip() for p in text.split(',')]
        ref = parts[0]
        mod_id = int(parts[1].lower().replace('mod', '').strip())
        
        await db.update_reference_mod(ref, mod_id)
        await messenger_api.send_text(sender_psid, f"Reference {ref} updated to Mod {mod_id}.")
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"Invalid format or not found. Error: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

async def prompt_delete_ref(sender_psid: str):
    await messenger_api.send_text(sender_psid, "Provide the 13-digit reference number you wish to delete.")
    state_manager.set_user_state(sender_psid, 'awaiting_delete_ref')

async def process_delete_ref(sender_psid: str, text: str):
    ref_number = text.strip()
    try:
        deleted = await db.delete_reference(ref_number)
        if deleted > 0:
            await messenger_api.send_text(sender_psid, f"✅ Reference {ref_number} deleted.")
        else:
            await messenger_api.send_text(sender_psid, f"❌ Reference {ref_number} not found.")
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"Error: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

# --- EDIT CLAIMS ---
async def prompt_edit_claims_ref(sender_psid: str):
    await messenger_api.send_text(sender_psid, "✍️ Enter the 13-digit reference number you want to edit claims for.")
    state_manager.set_user_state(sender_psid, 'awaiting_edit_claims_ref')

async def prompt_edit_claims_values(sender_psid: str, text: str):
    ref = await db.get_reference(text.strip())
    if not ref:
        return await messenger_api.send_text(sender_psid, "❌ Reference not found.")
        
    msg = f"Editing Ref: {ref['ref_number']}\nMod: {ref['mod_name']}\nCurrent Claims: {ref['claims_used']}/{ref['claims_max']}\n\nProvide new values: used,max (e.g., 1,3)"
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_edit_claims_values', ref_number=ref['ref_number'])

async def process_edit_claims_update(sender_psid: str, text: str):
    state = state_manager.get_user_state(sender_psid)
    try:
        used, maximum = map(int, [p.strip() for p in text.split(',')])
        if used > maximum:
            return await messenger_api.send_text(sender_psid, "❌ 'used' cannot be greater than 'max'.")
            
        await db.update_reference_claims(state['ref_number'], used, maximum)
        await messenger_api.send_text(sender_psid, f"✅ Claims for {state['ref_number']} updated to {used}/{maximum}.")
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Error: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)

# --- BULK REFERENCES ---
async def prompt_bulk_refs(sender_psid: str):
    mods = await db.get_mods()
    msg = "Available Mod IDs:\n" + "\n".join([f"- ID: {m['id']}" for m in mods])
    msg += "\nWhich mod to add bulk references to? Type Mod ID."
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_bulk_refs_mod_id')

async def process_bulk_refs_list(sender_psid: str, text: str):
    try:
        mod_id = int(text.strip())
        await messenger_api.send_text(sender_psid, f"Okay, adding refs to Mod {mod_id}. Send list now (separated by spaces/newlines).")
        state_manager.set_user_state(sender_psid, 'awaiting_bulk_refs_list', mod_id=mod_id)
    except Exception:
        await messenger_api.send_text(sender_psid, "Invalid Mod ID.")

async def process_bulk_refs_save(sender_psid: str, text: str):
    state = state_manager.get_user_state(sender_psid)
    import re
    ref_numbers = [r for r in re.split(r'[\s,\n]+', text.strip()) if r]
    
    try:
        result = await db.add_bulk_references(state['mod_id'], ref_numbers)
        summary = f"✅ Bulk import complete for Mod {state['mod_id']}.\n"
        summary += f"- Successfully added: {result['successfulAdds']}\n"
        if result['duplicates']: summary += f"- Duplicates skipped: {len(result['duplicates'])}\n"
        if result['invalids']: summary += f"- Invalid skipped: {len(result['invalids'])}\n"
        await messenger_api.send_text(sender_psid, summary)
    except Exception as e:
        await messenger_api.send_text(sender_psid, f"❌ Error: {e}")
    finally:
        state_manager.clear_user_state(sender_psid)
