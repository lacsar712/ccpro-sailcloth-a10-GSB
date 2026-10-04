from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClothRoll, DipRun, HygrometerSticker, Loft
from .permissions import IsAdminRole
from .rules import current_sticker
from .serializers import (
    ClothRollSerializer,
    DipRunPatchSerializer,
    DipRunSerializer,
    HygrometerStickerRenewSerializer,
    HygrometerStickerSerializer,
    LoftSerializer,
)

STICKER_EXISTS_MSG = "该帆布间已有现行未作废贴纸，请续期或先作废"


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
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = DipRun.objects.select_related("roll", "roll__loft").all()
        roll_id = self.request.query_params.get("rollId")
        if roll_id:
            qs = qs.filter(roll_id=roll_id)
        return qs

    def get_serializer_class(self):
        if self.action == "partial_update":
            return DipRunPatchSerializer
        return DipRunSerializer


class HygrometerStickerViewSet(viewsets.ModelViewSet):
    """湿度计止日贴纸：读全员；粘贴/续期/作废仅管理员。"""

    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = HygrometerSticker.objects.select_related("loft", "pasted_by").all()
        loft_id = self.request.query_params.get("loftId")
        current = self.request.query_params.get("current")
        if loft_id:
            qs = qs.filter(loft_id=loft_id)
        if current in ("1", "true", "yes"):
            qs = qs.filter(voided_at__isnull=True)
        return qs

    def get_serializer_class(self):
        if self.action == "partial_update":
            return HygrometerStickerRenewSerializer
        return HygrometerStickerSerializer

    def get_permissions(self):
        if self.action in ("create", "partial_update", "void"):
            return [IsAuthenticated(), IsAdminRole()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        loft = serializer.validated_data["loft"]
        if current_sticker(loft) is not None:
            return Response(
                {"detail": STICKER_EXISTS_MSG},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            # 唯一约束兜底并发粘贴：两请求交叉也只留一版
            with transaction.atomic():
                serializer.save(pasted_by=request.user)
        except IntegrityError:
            return Response(
                {"detail": STICKER_EXISTS_MSG},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        sticker = self.get_object()
        if sticker.voided_at is not None:
            return Response(
                {"detail": "该贴纸已作废，不能续期"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        sticker = self.get_object()
        if sticker.voided_at is not None:
            return Response(
                {"detail": "该贴纸已作废"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sticker.voided_at = timezone.now()
        sticker.save(update_fields=["voided_at"])
        serializer = HygrometerStickerSerializer(
            sticker, context=self.get_serializer_context()
        )
        return Response(serializer.data)


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
