from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import Bill, Building, FeeType, Payment, Reminder, Room


def make_number(prefix):
    return f"{prefix}{timezone.now().strftime('%Y%m%d%H%M%S%f')}"


def parse_period_to_date(period):
    parts = period.split("-")
    if len(parts) >= 2:
        try:
            year = int(parts[0])
            month = int(parts[1])
            return date(year, month, 1)
        except (ValueError, IndexError):
            pass
    return timezone.localdate()


def get_period_end_date(period):
    parts = period.split("-")
    if len(parts) >= 2:
        try:
            year = int(parts[0])
            month = int(parts[1])
            if month == 12:
                return date(year + 1, 1, 1) - timedelta(days=1)
            return date(year, month + 1, 1) - timedelta(days=1)
        except (ValueError, IndexError):
            pass
    return timezone.localdate()


def get_fee_type_by_period(name, period):
    period_end = get_period_end_date(period)
    return FeeType.get_active_version(name, period_end)


@transaction.atomic
def create_fee_type(name, billing_method, amount, cycle, effective_date=None, description=""):
    effective_date = effective_date or timezone.localdate()
    last_version = FeeType.objects.filter(name=name).order_by("-version").first()
    new_version = last_version.version + 1 if last_version else 1

    parent = None
    if last_version:
        parent = last_version.parent if last_version.parent else last_version

    fee_type = FeeType.objects.create(
        name=name,
        parent=parent,
        version=new_version,
        effective_date=effective_date,
        billing_method=billing_method,
        amount=amount,
        cycle=cycle,
        description=description,
        is_active=True,
    )

    FeeType.objects.filter(name=name).exclude(pk=fee_type.pk).update(is_active=False)

    return fee_type


@transaction.atomic
def update_fee_type(fee_type_id, **kwargs):
    fee_type = FeeType.objects.get(pk=fee_type_id)

    allowed_fields = {"billing_method", "amount", "cycle", "effective_date", "description", "name"}
    update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

    if not update_fields:
        return fee_type, False

    name = update_fields.get("name", fee_type.name)
    billing_method = update_fields.get("billing_method", fee_type.billing_method)
    amount = update_fields.get("amount", fee_type.amount)
    cycle = update_fields.get("cycle", fee_type.cycle)
    effective_date = update_fields.get("effective_date", fee_type.effective_date)
    description = update_fields.get("description", fee_type.description)

    has_bill = Bill.objects.filter(fee_type=fee_type).exists()
    if has_bill:
        new_fee_type = create_fee_type(
            name=name,
            billing_method=billing_method,
            amount=amount,
            cycle=cycle,
            effective_date=effective_date,
            description=description,
        )
        return new_fee_type, True

    for k, v in update_fields.items():
        setattr(fee_type, k, v)
    fee_type.save(update_fields=list(update_fields.keys()))
    return fee_type, False


@transaction.atomic
def generate_bills(fee_type_id, period, due_date, room_ids=None):
    fee_type = FeeType.objects.get(pk=fee_type_id)
    actual_fee_type = get_fee_type_by_period(fee_type.name, period)

    if actual_fee_type is None:
        raise ValueError(f"未找到 {fee_type.name} 在 {period} 账期的有效费用标准")

    rooms = Room.objects.filter(is_active=True)
    if room_ids:
        rooms = rooms.filter(id__in=room_ids)

    created = []
    skipped = 0
    snapshot = actual_fee_type.get_snapshot()
    for room in rooms.select_related("building"):
        amount = actual_fee_type.calculate_amount(room)
        bill, was_created = Bill.objects.get_or_create(
            room=room,
            fee_type=actual_fee_type,
            period=period,
            defaults={
                "bill_no": make_number("B"),
                "amount": amount,
                "due_date": due_date,
                "status": Bill.UNPAID,
                "fee_type_snapshot": snapshot,
            },
        )
        if was_created:
            created.append(bill)
        else:
            skipped += 1
    return created, skipped, actual_fee_type


@transaction.atomic
def pay_bill(bill, method, payer=""):
    if bill.status == Bill.PAID:
        raise ValueError("该账单已缴费")
    if bill.status == Bill.CANCELLED:
        raise ValueError("作废账单不能缴费")

    payment = Payment.objects.create(
        payment_no=make_number("P"),
        bill=bill,
        amount=bill.amount,
        method=method,
        payer=payer or bill.room.owner_name,
        receipt_no=make_number("R"),
    )
    bill.status = Bill.PAID
    bill.paid_at = payment.paid_at
    bill.save(update_fields=["status", "paid_at"])
    return payment


@transaction.atomic
def create_overdue_reminders(channel=Reminder.SMS):
    today = timezone.localdate()
    overdue = Bill.objects.filter(status__in=[Bill.UNPAID, Bill.OVERDUE], due_date__lt=today).select_related(
        "room", "room__building", "fee_type"
    )
    reminders = []
    for bill in overdue:
        bill.status = Bill.OVERDUE
        bill.save(update_fields=["status"])
        message = (
            f"{bill.room.owner_name}您好，您位于{bill.room.building.name}-{bill.room.room_no}的"
            f"{bill.period}{bill.fee_type.name}欠费{bill.amount}元，请尽快缴纳。"
        )
        reminders.append(
            Reminder.objects.create(
                reminder_no=make_number("D"),
                bill=bill,
                channel=channel,
                message=message,
            )
        )
    return reminders


def dashboard_stats():
    today = timezone.localdate()
    Bill.objects.filter(status=Bill.UNPAID, due_date__lt=today).update(status=Bill.OVERDUE)

    bills = Bill.objects.all()
    paid_total = Payment.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    receivable_total = bills.exclude(status=Bill.CANCELLED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    unpaid_total = bills.filter(status__in=[Bill.UNPAID, Bill.OVERDUE]).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    status_counts = dict(bills.values_list("status").annotate(total=Count("id")))
    recent_bills = bills.select_related("room", "room__building", "fee_type")[:8]

    return {
        "building_count": Building.objects.count(),
        "room_count": Room.objects.count(),
        "bill_count": bills.count(),
        "paid_total": paid_total,
        "receivable_total": receivable_total,
        "unpaid_total": unpaid_total,
        "overdue_count": bills.filter(status=Bill.OVERDUE).count(),
        "status_counts": {
            "unpaid": status_counts.get(Bill.UNPAID, 0),
            "paid": status_counts.get(Bill.PAID, 0),
            "overdue": status_counts.get(Bill.OVERDUE, 0),
            "cancelled": status_counts.get(Bill.CANCELLED, 0),
        },
        "rooms_with_debt": Room.objects.filter(bills__status__in=[Bill.UNPAID, Bill.OVERDUE]).distinct().count(),
        "recent_bills": recent_bills,
    }
