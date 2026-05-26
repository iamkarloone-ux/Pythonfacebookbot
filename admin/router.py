import state_manager
import messenger_api
from admin import mod_manager, ref_manager, operations

async def handle_admin_message(sender_psid: str, lower_text: str, received_text: str):
    state_obj = state_manager.get_user_state(sender_psid)
    state = state_obj["state"] if state_obj else None

    # 1. Global Cancel
    if lower_text == 'menu':
        state_manager.clear_user_state(sender_psid)
        return await operations.show_admin_menu(sender_psid)
    if lower_text == 'my id':
        return await messenger_api.send_text(sender_psid, f"Your Facebook Page-Scoped ID is: {sender_psid}")

    # 2. State-Based Routing (If Admin is in the middle of a process)
    if state:
        # -- Operations / General --
        if state == 'awaiting_reply_psid': return await operations.prompt_reply_username(sender_psid, received_text)
        elif state == 'awaiting_reply_username': return await operations.prompt_reply_password(sender_psid, received_text)
        elif state == 'awaiting_reply_password': return await operations.process_reply_send(sender_psid, received_text)
        elif state == 'awaiting_pause_toggle_psid': return await operations.process_pause_toggle(sender_psid, received_text)
        elif state == 'awaiting_broadcast_message': return await operations.process_broadcast_confirm(sender_psid, received_text)
        elif state == 'awaiting_broadcast_confirmation': return await operations.process_broadcast_execute(sender_psid, received_text)
        elif state == 'awaiting_sales_stats_period': return await operations.process_sales_stats(sender_psid, lower_text)
        elif state == 'awaiting_admin_create_email': return await operations.prompt_admin_create_mod(sender_psid, received_text)
        elif state == 'awaiting_admin_create_mod_id': return await operations.process_admin_create(sender_psid, received_text)
        
        # -- Mod Manager --
        elif state == 'awaiting_add_mod': return await mod_manager.process_add_mod(sender_psid, received_text)
        elif state == 'awaiting_edit_mod_id': return await mod_manager.process_edit_mod_detail(sender_psid, received_text)
        elif state == 'awaiting_edit_mod_detail_choice': return await mod_manager.process_edit_mod_value(sender_psid, lower_text)
        elif state == 'awaiting_edit_mod_new_value': return await mod_manager.process_edit_mod_save(sender_psid, received_text)
        elif state == 'awaiting_edit_mod_continue': return await mod_manager.process_edit_mod_continue(sender_psid, lower_text)
        
        # -- Reference Manager --
        elif state == 'viewing_references':
            page = state_obj.get("page", 1)
            if lower_text == '1': return await ref_manager.handle_view_references(sender_psid, page + 1)
            if lower_text == '2': return await ref_manager.handle_view_references(sender_psid, page - 1)
        elif state == 'awaiting_add_ref_number': return await ref_manager.process_add_ref_mod(sender_psid, received_text)
        elif state == 'awaiting_add_ref_mod_id': return await ref_manager.process_add_ref_save(sender_psid, received_text)
        elif state == 'awaiting_edit_ref': return await ref_manager.process_edit_ref(sender_psid, received_text)
        elif state == 'awaiting_delete_ref': return await ref_manager.process_delete_ref(sender_psid, received_text)
        elif state == 'awaiting_bulk_refs_mod_id': return await ref_manager.process_bulk_refs_list(sender_psid, received_text)
        elif state == 'awaiting_bulk_refs_list': return await ref_manager.process_bulk_refs_save(sender_psid, received_text)
        elif state == 'awaiting_edit_claims_ref': return await ref_manager.prompt_edit_claims_values(sender_psid, received_text)
        elif state == 'awaiting_edit_claims_values': return await ref_manager.process_edit_claims_update(sender_psid, received_text)
        elif state == 'awaiting_edit_admin': return await operations.process_edit_admin(sender_psid, received_text)
        
        return # Do nothing if state doesn't match

    # 3. Menu Command Routing (If Admin is NOT in a state)
    commands = {
        '1': lambda: ref_manager.handle_view_references(sender_psid, 1),
        '3': lambda: mod_manager.prompt_edit_mod(sender_psid),
        '4': lambda: ref_manager.prompt_add_ref(sender_psid),
        '5': lambda: operations.prompt_edit_admin(sender_psid),
        '6': lambda: ref_manager.prompt_edit_ref(sender_psid),
        '7': lambda: mod_manager.prompt_add_mod(sender_psid),
        '8': lambda: ref_manager.prompt_delete_ref(sender_psid),
        '9': lambda: operations.toggle_admin_status(sender_psid),
        '10': lambda: operations.prompt_reply_psid(sender_psid),
        '11': lambda: operations.handle_view_jobs(sender_psid),
        '12': lambda: operations.prompt_admin_create_email(sender_psid),
        '13': lambda: ref_manager.prompt_bulk_refs(sender_psid),
        '14': lambda: operations.prompt_pause_toggle(sender_psid),
        '15': lambda: operations.toggle_maintenance(sender_psid),
        '17': lambda: operations.prompt_broadcast(sender_psid),
        '18': lambda: ref_manager.prompt_edit_claims_ref(sender_psid),
        '19': lambda: operations.prompt_sales_stats(sender_psid),
    }

    action = commands.get(lower_text)
    if action:
        await action()
    else:
        await operations.show_admin_menu(sender_psid)
