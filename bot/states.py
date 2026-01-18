from aiogram.fsm.state import State, StatesGroup

class AddObjectState(StatesGroup):
    waiting_for_address = State()

class AddStayState(StatesGroup):
    waiting_for_tenant_id = State()
    waiting_for_object_id = State() # or selection
    waiting_for_rent_amount = State()
    waiting_for_tax_rate = State()
    waiting_for_rent_day = State()

class EditObjectState(StatesGroup):
    waiting_for_address = State()

class EditStayState(StatesGroup):
    waiting_for_rent_amount = State()
    waiting_for_tax_rate = State()
    waiting_for_rent_day = State()

class ReceiptState(StatesGroup):
    waiting_for_photo = State()
    confirm_type = State()

class EditTenantState(StatesGroup):
    waiting_for_fullname = State()

class AddTenantState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()

class GuestState(StatesGroup):
    waiting_for_code = State()

class AddContactState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()

class InviteAdminState(StatesGroup):
    waiting_for_contact = State()

class InviteTenantState(StatesGroup):
    waiting_for_contact = State()
    waiting_for_object = State()

class SupportState(StatesGroup):
    waiting_for_message = State()
    admin_replying = State()


class AdminMessageState(StatesGroup):
    waiting_for_text = State()


class ManualPaymentState(StatesGroup):
    waiting_for_amount = State()

class AddRSOState(StatesGroup):
    waiting_for_name = State()
    waiting_for_service_type = State()
    waiting_for_inn = State()

class LinkRSOState(StatesGroup):
    waiting_for_provider_selection = State()
    waiting_for_account_number = State()

class AddUKState(StatesGroup):
    waiting_for_name = State()
    waiting_for_inn = State()

class CancelPaymentState(StatesGroup):
    waiting_for_reason = State()

class ApproveReceiptState(StatesGroup):
    waiting_for_amount = State()

class RejectReceiptState(StatesGroup):
    waiting_for_reason = State()
