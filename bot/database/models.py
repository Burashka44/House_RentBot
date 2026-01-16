import enum
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import BigInteger, String, Boolean, ForeignKey, Integer, Numeric, Date, DateTime, JSON, Text, DATE, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from bot.database.core import Base

# Enums
class TenantStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    banned = "banned"
    privacy_revoked = "privacy_revoked"

class ObjectStatus(str, enum.Enum):
    free = "free"
    occupied = "occupied"
    repair = "repair"

class StayStatus(str, enum.Enum):
    active = "active"
    archived = "archived"

class ChargeStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"

class PaymentType(str, enum.Enum):
    rent = "rent"
    comm = "comm"

class PaymentStatus(str, enum.Enum):
    pending_manual = "pending_manual"
    confirmed = "confirmed"
    auto_confirmed = "auto_confirmed"
    rejected = "rejected"

class ReceiptDecision(str, enum.Enum):
    accepted = "accepted"
    rejected = "rejected"

class Role(str, enum.Enum):
    tenant = "tenant"
    admin = "admin"
    owner = "owner"
    manager = "manager"

class UserRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    manager = "manager"

class CommServiceType(str, enum.Enum):
    electric = "electric"
    water = "water"
    heating = "heating"
    garbage = "garbage"
    internet = "internet"
    tv = "tv"
    phone = "phone"
    other = "other"


# 3.1 Tenant
class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    tg_username: Mapped[Optional[str]] = mapped_column(String)
    full_name: Mapped[str] = mapped_column(String)
    phone: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    passport_data: Mapped[Optional[str]] = mapped_column(String)  # Simple string for MVP
    
    status: Mapped[TenantStatus] = mapped_column(String, default=TenantStatus.active.value)
    
    personal_data_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[Optional[str]] = mapped_column(String)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stays: Mapped[List["TenantStay"]] = relationship(back_populates="tenant")


# 3.2 Object
class RentalObject(Base): # Renamed to avoid reserved word 'Object' confusion
    __tablename__ = "objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer) # External logic or simple config
    address: Mapped[str] = mapped_column(String)
    status: Mapped[ObjectStatus] = mapped_column(String, default=ObjectStatus.free.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    settings: Mapped["ObjectSettings"] = relationship(back_populates="rental_object", uselist=False)
    stays: Mapped[List["TenantStay"]] = relationship(back_populates="rental_object")
    comm_providers: Mapped[List["CommProvider"]] = relationship(back_populates="rental_object")


# 3.3 ObjectSettings
class ObjectSettings(Base):
    __tablename__ = "object_settings"

    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id"), primary_key=True)
    comm_bill_day: Mapped[int] = mapped_column(Integer, default=22)
    min_ready_ratio: Mapped[float] = mapped_column(Numeric(3, 2), default=0.7)
    max_comm_reminders: Mapped[int] = mapped_column(Integer, default=2)

    rental_object: Mapped["RentalObject"] = relationship(back_populates="settings")


# 3.4 TenantStay
class TenantStay(Base):
    __tablename__ = "tenant_stays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    
    date_from: Mapped[date] = mapped_column(DATE)
    date_to: Mapped[Optional[date]] = mapped_column(DATE, nullable=True)
    
    rent_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    rent_day: Mapped[int] = mapped_column(Integer)
    comm_day: Mapped[int] = mapped_column(Integer)
    
    notifications_mode: Mapped[str] = mapped_column(String, default="full")
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)
    status: Mapped[StayStatus] = mapped_column(String, default=StayStatus.active.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="stays")
    rental_object: Mapped["RentalObject"] = relationship(back_populates="stays")
    
    rent_charges: Mapped[List["RentCharge"]] = relationship(back_populates="stay")
    comm_charges: Mapped[List["CommCharge"]] = relationship(back_populates="stay")
    payments: Mapped[List["Payment"]] = relationship(back_populates="stay")
    receipts: Mapped[List["PaymentReceipt"]] = relationship(back_populates="stay")
    messages: Mapped[List["SupportMessage"]] = relationship(back_populates="stay")
    occupants: Mapped[List["StayOccupant"]] = relationship(back_populates="stay", cascade="all, delete-orphan")

    @property
    def primary_tenant(self) -> Optional["Tenant"]:
        """Primary tenant (backward compatibility and convenience)"""
        for occupant in self.occupants:
            if occupant.role == "primary" and occupant.left_date is None:
                return occupant.tenant
        return None
    
    @property
    def active_occupants(self) -> List["StayOccupant"]:
        """Get all currently active occupants (not yet left)"""
        return [o for o in self.occupants if o.left_date is None]


# 3.4.1 StayOccupant (Intermediate table for multi-tenant stays)
class StayOccupant(Base):
    __tablename__ = "stay_occupants"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stay_id: Mapped[int] = mapped_column(ForeignKey("tenant_stays.id", ondelete="CASCADE"))
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    
    role: Mapped[str] = mapped_column(String, default="co-tenant")  # "primary" or "co-tenant"
    joined_date: Mapped[date] = mapped_column(DATE)
    left_date: Mapped[Optional[date]] = mapped_column(DATE, nullable=True)
    
    # Individual notification preferences
    receive_rent_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    receive_comm_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    receive_meter_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('stay_id', 'tenant_id', name='uq_stay_tenant'),
    )
    
    # Relationships
    stay: Mapped["TenantStay"] = relationship(back_populates="occupants")
    tenant: Mapped["Tenant"] = relationship()


# 3.5 CommProvider
class CommProvider(Base):
    __tablename__ = "comm_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_id: Mapped[Optional[int]] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), nullable=True)
    service_type: Mapped[CommServiceType] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    short_keywords: Mapped[List[str]] = mapped_column(JSON, default=[]) # List of strings
    account_number: Mapped[Optional[str]] = mapped_column(String)
    source: Mapped[Optional[str]] = mapped_column(String, default="manual")  # 'kvartplata', 'gis_zkh', 'manual'
    
    # Payment Details (Added in migration add_payment_details_rso)
    inn: Mapped[Optional[str]] = mapped_column(String)
    bik: Mapped[Optional[str]] = mapped_column(String)
    bank_account: Mapped[Optional[str]] = mapped_column(String)
    payment_purpose_template: Mapped[Optional[str]] = mapped_column(Text)
    yoomoney_service_id: Mapped[Optional[str]] = mapped_column(String)
    
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    rental_object: Mapped["RentalObject"] = relationship(back_populates="comm_providers")
    charges: Mapped[List["CommCharge"]] = relationship(back_populates="provider")


# 3.6 RentCharge
class RentCharge(Base):
    __tablename__ = "rent_charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stay_id: Mapped[int] = mapped_column(ForeignKey("tenant_stays.id"))
    month: Mapped[date] = mapped_column(DATE) # First day of month
    amount: Mapped[float] = mapped_column(Numeric(12, 2)) # Total Amount
    base_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2)) # Amount without tax
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    tax_rate_snapshot: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    status: Mapped[ChargeStatus] = mapped_column(String, default=ChargeStatus.pending.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stay: Mapped["TenantStay"] = relationship(back_populates="rent_charges")


# 3.7 CommCharge
class CommCharge(Base):
    __tablename__ = "comm_charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stay_id: Mapped[int] = mapped_column(ForeignKey("tenant_stays.id"))
    provider_id: Mapped[int] = mapped_column(ForeignKey("comm_providers.id"))
    service_type: Mapped[CommServiceType] = mapped_column(String)
    month: Mapped[date] = mapped_column(DATE)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[ChargeStatus] = mapped_column(String, default=ChargeStatus.pending.value)
    source: Mapped[str] = mapped_column(String, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stay: Mapped["TenantStay"] = relationship(back_populates="comm_charges")
    provider: Mapped["CommProvider"] = relationship(back_populates="charges")


# 3.8 Payment
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stay_id: Mapped[int] = mapped_column(ForeignKey("tenant_stays.id"))
    type: Mapped[PaymentType] = mapped_column(String)
    
    # Generic FK not easily supported in simple SQLAlchemy, so we can use ID or nullable FKs.
    # We will use specific FKs
    rent_charge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rent_charges.id"), nullable=True)
    comm_charge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("comm_charges.id"), nullable=True)
    
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    
    # New: Partial payment support
    total_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)  # Total paid
    allocated_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)  # Distributed
    unallocated_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)  # Advance
    
    method: Mapped[str] = mapped_column(String, default="online")
    status: Mapped[PaymentStatus] = mapped_column(String, default=PaymentStatus.pending_manual.value)
    source: Mapped[str] = mapped_column(String, default="photo")
    
    # Manual payment marking (for admin-marked payments without receipt)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    marked_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # admin tg_id
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    meta_json: Mapped[Optional[dict]] = mapped_column(JSON) # Additional details

    stay: Mapped["TenantStay"] = relationship(back_populates="payments")
    receipt: Mapped[Optional["PaymentReceipt"]] = relationship(back_populates="payment", uselist=False)
    allocations: Mapped[List["PaymentAllocation"]] = relationship(back_populates="payment", cascade="all, delete-orphan")


# 3.8.1 PaymentAllocation
class PaymentAllocation(Base):
    """Tracks payment distribution across charges (partial payments)"""
    __tablename__ = "payment_allocations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"))
    
    charge_id: Mapped[int] = mapped_column(Integer, nullable=False)
    charge_type: Mapped[str] = mapped_column(String)  # "rent" or "comm"
    
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    payment: Mapped["Payment"] = relationship(back_populates="allocations")


# 3.9 PaymentReceipt
class PaymentReceipt(Base):
    __tablename__ = "payment_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("payments.id"), unique=True, nullable=True)
    stay_id: Mapped[int] = mapped_column(ForeignKey("tenant_stays.id"))
    
    file_id: Mapped[str] = mapped_column(String)
    file_type: Mapped[str] = mapped_column(String) # photo, document
    
    ocr_text: Mapped[Optional[str]] = mapped_column(Text)
    ocr_conf: Mapped[Optional[float]] = mapped_column(Numeric(4, 3))
    
    parsed_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    parsed_date: Mapped[Optional[date]] = mapped_column(DATE)
    parsed_receiver: Mapped[Optional[str]] = mapped_column(String)
    parsed_purpose: Mapped[Optional[str]] = mapped_column(String)
    parsed_raw_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    decision: Mapped[ReceiptDecision] = mapped_column(String)
    reject_reason: Mapped[Optional[str]] = mapped_column(String)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stay: Mapped["TenantStay"] = relationship(back_populates="receipts")
    payment: Mapped["Payment"] = relationship(back_populates="receipt")


# 3.10 RentReceiver
class RentReceiver(Base):
    __tablename__ = "rent_receivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer)
    # If None, global for this owner
    object_id: Mapped[Optional[int]] = mapped_column(ForeignKey("objects.id"), nullable=True) 
    
    full_name: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String)
    tg_username: Mapped[Optional[str]] = mapped_column(String)
    card_last4: Mapped[Optional[str]] = mapped_column(String)
    card_bank: Mapped[Optional[str]] = mapped_column(String)
    yoomoney_acc: Mapped[Optional[str]] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# 3.11 SupportMessage
class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stay_id: Mapped[int] = mapped_column(ForeignKey("tenant_stays.id"))
    from_role: Mapped[Role] = mapped_column(String)
    text: Mapped[Optional[str]] = mapped_column(Text)
    
    is_read_by_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read_by_tenant: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stay: Mapped["TenantStay"] = relationship(back_populates="messages")
    attachments: Mapped[List["SupportAttachment"]] = relationship(back_populates="message")


# 3.12 SupportAttachment
class SupportAttachment(Base):
    __tablename__ = "support_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("support_messages.id"))
    file_id: Mapped[str] = mapped_column(String)
    file_type: Mapped[str] = mapped_column(String)

    message: Mapped["SupportMessage"] = relationship(back_populates="attachments")


# ========== UK and RSO System Models ==========

# UK Companies (Management Companies)
class UKCompany(Base):
    __tablename__ = "uk_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    inn: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    website: Mapped[Optional[str]] = mapped_column(String)
    address: Mapped[Optional[str]] = mapped_column(String)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    houses: Mapped[List["House"]] = relationship(back_populates="uk_company")
    rso_links: Mapped[List["UKRSOLink"]] = relationship(back_populates="uk_company")


# Houses (for address normalization and UK detection)
class House(Base):
    __tablename__ = "houses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region: Mapped[Optional[str]] = mapped_column(String)
    city: Mapped[str] = mapped_column(String, nullable=False, index=True)
    street: Mapped[str] = mapped_column(String, nullable=False, index=True)
    house_number: Mapped[str] = mapped_column(String, nullable=False)  # Can include letters: 12А, 5/7
    uk_id: Mapped[Optional[int]] = mapped_column(ForeignKey("uk_companies.id"), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    uk_company: Mapped[Optional["UKCompany"]] = relationship(back_populates="houses")


# UK to RSO Links (which providers are used by which UK)
class UKRSOLink(Base):
    __tablename__ = "uk_rso_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uk_id: Mapped[int] = mapped_column(ForeignKey("uk_companies.id"), nullable=False)
    provider_id: Mapped[int] = mapped_column(ForeignKey("comm_providers.id"), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    uk_company: Mapped["UKCompany"] = relationship(back_populates="rso_links")

    __table_args__ = (
        UniqueConstraint('uk_id', 'provider_id', name='uq_uk_rso'),
    )


# Object to RSO Links (which providers are assigned to an object)
class ObjectRSOLink(Base):
    __tablename__ = "object_rso_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), nullable=False)
    provider_id: Mapped[int] = mapped_column(ForeignKey("comm_providers.id", ondelete="CASCADE"), nullable=False)
    
    # Specific account number for this object with this provider
    account_number: Mapped[Optional[str]] = mapped_column(String, nullable=True) # Legacy/Alternative
    
    # Payment Details (Added in migration add_payment_details_rso)
    personal_account: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contract_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    service_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payment_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('object_id', 'provider_id', name='uq_object_rso'),
    )

    provider: Mapped["CommProvider"] = relationship()


# 3.13 InviteCode (Onboarding)
class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    
    # tenant_id is nullable because code might be for a new admin
    tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    object_id: Mapped[Optional[int]] = mapped_column(ForeignKey("objects.id"), nullable=True)
    
    role: Mapped[str] = mapped_column(String, default="tenant")  # "tenant" or "admin"
    
    created_by: Mapped[int] = mapped_column(Integer) # Admin ID (tg_id) who created it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", foreign_keys=[tenant_id])


# 3.14 User (Admin/Owner/Manager)
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    tg_username: Mapped[Optional[str]] = mapped_column(String)
    full_name: Mapped[str] = mapped_column(String)
    
    role: Mapped[UserRole] = mapped_column(String, default=UserRole.admin.value)
    
    # Permissions (JSON for flexibility)
    permissions: Mapped[Optional[dict]] = mapped_column(JSON, default={})
    
    # Who created this admin (for audit)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# 3.15 TenantSettings
class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    
    # Notification preferences
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rent_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    comm_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Days before due date to send reminder (default: 3 days)
    reminder_days: Mapped[int] = mapped_column(Integer, default=3)
    
    # How many times to remind per day (default: 1)
    reminder_count: Mapped[int] = mapped_column(Integer, default=1)
    
    # Preferred contact time (optional)
    preferred_time: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    tenant: Mapped["Tenant"] = relationship("Tenant", backref="settings")



# 3.16 ServiceSubscription (tenant's active services)
class ServiceSubscription(Base):
    __tablename__ = "service_subscriptions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stay_id: Mapped[int] = mapped_column(ForeignKey("tenant_stays.id"))
    provider_id: Mapped[int] = mapped_column(ForeignKey("comm_providers.id"))
    
    # Tenant can disable specific services
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Personal account number if different from provider default
    account_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    stay: Mapped["TenantStay"] = relationship("TenantStay")
    provider: Mapped["CommProvider"] = relationship("CommProvider")


# 3.17 AdminContact (Contact information for display)
class AdminContact(Base):
    __tablename__ = "admin_contacts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    telegram: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

