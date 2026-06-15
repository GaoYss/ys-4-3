from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from communities.models import Bill, Building, FeeType, Room
from communities.services import create_fee_type, generate_bills, get_fee_type_by_period, pay_bill


class Command(BaseCommand):
    help = "Create demo buildings, rooms, fee types, bills, payments and reminders."

    def handle(self, *args, **options):
        building, _ = Building.objects.get_or_create(
            name="1号楼",
            defaults={"address": "幸福小区东区", "floor_count": 18, "unit_count": 2, "manager": "王管家"},
        )
        room_a, _ = Room.objects.get_or_create(
            building=building,
            room_no="1-101",
            defaults={"owner_name": "张三", "phone": "13800000001", "area": Decimal("96.50")},
        )
        Room.objects.get_or_create(
            building=building,
            room_no="1-102",
            defaults={"owner_name": "李四", "phone": "13800000002", "area": Decimal("88.20")},
        )

        existing_active = FeeType.objects.filter(name="物业费", is_active=True).first()
        if existing_active:
            fee = existing_active
        elif FeeType.objects.filter(name="物业费").exists():
            fee = FeeType.objects.filter(name="物业费").order_by("-effective_date", "-version").first()
            fee.is_active = True
            fee.save(update_fields=["is_active"])
            FeeType.objects.filter(name="物业费").exclude(pk=fee.pk).update(is_active=False)
        else:
            fee = create_fee_type(
                name="物业费",
                billing_method=FeeType.AREA,
                amount=Decimal("2.80"),
                cycle=FeeType.MONTHLY,
                effective_date=date(2026, 1, 1),
                description="物业综合服务费",
            )

        period = "2026-06"
        actual_fee = get_fee_type_by_period("物业费", period) or fee
        created, skipped, _ = generate_bills(actual_fee.id, period, date(2026, 6, 30))
        bill = Bill.objects.filter(room=room_a, period=period).order_by("-generated_at").first()
        if bill and bill.status != Bill.PAID:
            pay_bill(bill, "wechat", room_a.owner_name)

        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
