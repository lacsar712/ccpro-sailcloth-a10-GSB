from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClothRoll, DipRun, HygrometerSticker, Loft
from .permissions import IsAdminRole
from .serializers import (
    ClothRollSerializer,
    DipRunSerializer,
    HygrometerStickerSerializer,
    LoftSerializer,
    StickerRenewSerializer,
)

MSG_STICKER_EXISTS = "该帆布间已有现行贴纸，请先作废或使用续期"
MSG_STICKER_VOIDED = "该贴纸已作废，不能续期"
MSG_STICKER_NOT_CURRENT = "该贴纸已作废，不能重复作废"


class LoftViewSet(viewsets.ModelViewSet):
    queryset = Loft.objects.annotate(roll_count=Count("rolls")).all()
    serializer_class = LoftSerializer


class ClothRollViewSet(viewsets.ModelViewSet):
    serializer_class = ClothRollSerializer

    def get_queryset(self):
        qs = ClothRoll.objects.select_related("loft").all()
        loft_id = self.request.query_params.get("loftId")
        status = self.request.query_params.get("status")
        if loft_id:
            qs = qs.filter(loft_id=loft_id)
        if status:
            qs = qs.filter(status=status)
        return qs


class DipRunViewSet(viewsets.ModelViewSet):
    serializer_class = DipRunSerializer
    # 开放 PATCH 以支持补写/改写固化时长；写时长受贴纸规则拦截（见序列化器）
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = DipRun.objects.select_related("roll", "roll__loft").all()
        roll_id = self.request.query_params.get("rollId")
        if roll_id:
            qs = qs.filter(roll_id=roll_id)
        return qs


class HygrometerStickerViewSet(viewsets.ModelViewSet):
    """止日贴纸：读取全员可见；粘贴/续期/作废仅管理员。"""

    serializer_class = HygrometerStickerSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.action in ("create", "renew", "void"):
            return [IsAuthenticated(), IsAdminRole()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = HygrometerSticker.objects.select_related("loft", "pasted_by").all()
        loft_id = self.request.query_params.get("loftId")
        current = self.request.query_params.get("current")
        if loft_id:
            qs = qs.filter(loft_id=loft_id)
        if current in ("1", "true"):
            qs = qs.filter(voided_at__isnull=True)
        return qs

    def _lock_loft(self, loft_id):
        # 同一帆布间的粘贴/续期/作废都先抢同一行锁，串行化后库里只留一版
        return Loft.objects.select_for_update().get(pk=loft_id)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                loft = self._lock_loft(data["loft"].pk)
                if loft.hygrometer_stickers.filter(voided_at__isnull=True).exists():
                    return Response({"detail": MSG_STICKER_EXISTS}, status=400)
                sticker = HygrometerSticker.objects.create(
                    loft=loft,
                    instrument_no=data["instrument_no"],
                    stop_date=data["stop_date"],
                    pasted_by=request.user,
                )
        except IntegrityError:
            return Response({"detail": MSG_STICKER_EXISTS}, status=400)
        return Response(self.get_serializer(sticker).data, status=201)

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        sticker = get_object_or_404(HygrometerSticker, pk=pk)
        serializer = StickerRenewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            loft = self._lock_loft(sticker.loft_id)
            current = loft.hygrometer_stickers.filter(voided_at__isnull=True).first()
            if current is None or current.pk != sticker.pk:
                return Response({"detail": MSG_STICKER_VOIDED}, status=400)
            current.stop_date = data["stop_date"]
            if data.get("instrument_no"):
                current.instrument_no = data["instrument_no"]
            current.pasted_by = request.user
            current.save(update_fields=["stop_date", "instrument_no", "pasted_by", "updated_at"])
        return Response(self.get_serializer(current).data)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        sticker = get_object_or_404(HygrometerSticker, pk=pk)
        with transaction.atomic():
            loft = self._lock_loft(sticker.loft_id)
            current = loft.hygrometer_stickers.filter(voided_at__isnull=True).first()
            if current is None or current.pk != sticker.pk:
                return Response({"detail": MSG_STICKER_NOT_CURRENT}, status=400)
            current.voided_at = timezone.now()
            current.save(update_fields=["voided_at", "updated_at"])
        return Response(self.get_serializer(current).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    data = {
        "loftCount": Loft.objects.count(),
        "rawRollCount": ClothRoll.objects.filter(status=ClothRoll.STATUS_RAW).count(),
        "dippingRollCount": ClothRoll.objects.filter(
            status=ClothRoll.STATUS_DIPPING
        ).count(),
        "curedRollCount": ClothRoll.objects.filter(status=ClothRoll.STATUS_CURED).count(),
        "dipRunCount": DipRun.objects.count(),
    }
    return Response(data)
