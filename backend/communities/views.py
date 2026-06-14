from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import Bill, Building, FeeType, Payment, Reminder, Room
from .serializers import (
    BillSerializer,
    BuildingDetailSerializer,
    BuildingSerializer,
    FeeTypeSerializer,
    PaymentSerializer,
    ReminderSerializer,
    RoomSerializer,
)
from .services import create_fee_type, create_overdue_reminders, dashboard_stats, generate_bills, pay_bill, update_fee_type


class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.annotate(room_count=Count("rooms")).all()
    serializer_class = BuildingSerializer

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BuildingDetailSerializer
        return BuildingSerializer


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.select_related("building").all()
    serializer_class = RoomSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        building = self.request.query_params.get("building")
        if building:
            queryset = queryset.filter(building_id=building)
        return queryset


class FeeTypeViewSet(viewsets.ModelViewSet):
    queryset = FeeType.objects.all()
    serializer_class = FeeTypeSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        name = self.request.query_params.get("name")
        if name:
            queryset = queryset.filter(name=name)
        return queryset

    def create(self, request, *args, **kwargs):
        try:
            fee_type = create_fee_type(
                name=request.data.get("name"),
                billing_method=request.data.get("billing_method"),
                amount=request.data.get("amount"),
                cycle=request.data.get("cycle"),
                effective_date=request.data.get("effective_date"),
                description=request.data.get("description", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(fee_type).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        try:
            updated_instance, created_new = update_fee_type(instance.id, **request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(updated_instance)
        return Response({
            **serializer.data,
            "created_new_version": created_new,
            "message": "已创建新版本" if created_new else "已更新"
        })

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        fee_type = self.get_object()
        queryset = FeeType.objects.filter(name=fee_type.name).order_by("-effective_date", "-version")
        return Response(self.get_serializer(queryset, many=True).data)


class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.select_related("room", "room__building", "fee_type").all()
    serializer_class = BillSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        period = self.request.query_params.get("period")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if period:
            queryset = queryset.filter(period=period)
        return queryset

    @action(detail=False, methods=["post"])
    def generate(self, request):
        fee_type_id = request.data.get("fee_type")
        period = request.data.get("period")
        due_date = request.data.get("due_date")
        room_ids = request.data.get("room_ids")
        if not all([fee_type_id, period, due_date]):
            return Response({"detail": "fee_type、period、due_date 为必填项"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            created, skipped, actual_fee_type = generate_bills(fee_type_id, period, due_date, room_ids)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "created": BillSerializer(created, many=True).data,
                "created_count": len(created),
                "skipped_count": skipped,
                "fee_type_used": FeeTypeSerializer(actual_fee_type).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        bill = self.get_object()
        try:
            payment = pay_bill(bill, request.data.get("method", Payment.WECHAT), request.data.get("payer", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("bill", "bill__room", "bill__room__building", "bill__fee_type").all()
    serializer_class = PaymentSerializer

    def create(self, request, *args, **kwargs):
        bill = get_object_or_404(Bill.objects.select_related("room"), pk=request.data.get("bill"))
        try:
            payment = pay_bill(bill, request.data.get("method", Payment.WECHAT), request.data.get("payer", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)


class ReminderViewSet(viewsets.ModelViewSet):
    queryset = Reminder.objects.select_related("bill", "bill__room", "bill__room__building", "bill__fee_type").all()
    serializer_class = ReminderSerializer

    @action(detail=False, methods=["post"])
    def create_overdue(self, request):
        reminders = create_overdue_reminders(request.data.get("channel", Reminder.SMS))
        return Response(
            {"created_count": len(reminders), "created": ReminderSerializer(reminders, many=True).data},
            status=status.HTTP_201_CREATED,
        )


@api_view(["GET"])
def dashboard(request):
    stats = dashboard_stats()
    recent = BillSerializer(stats.pop("recent_bills"), many=True).data
    return Response({**stats, "recent_bills": recent})
