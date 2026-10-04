from django.utils import timezone
from rest_framework import serializers

from .models import ClothRoll, DipRun, HygrometerSticker, Loft
from .rules import can_mark_roll_cured, cure_hours_block_message


class LoftSerializer(serializers.ModelSerializer):
    rollCount = serializers.SerializerMethodField()

    class Meta:
        model = Loft
        fields = ("id", "name", "location", "notes", "rollCount", "created_at")
        read_only_fields = ("id", "rollCount", "created_at")

    def get_rollCount(self, obj):
        if hasattr(obj, "roll_count"):
            return obj.roll_count
        return obj.rolls.count()


class ClothRollSerializer(serializers.ModelSerializer):
    loftId = serializers.PrimaryKeyRelatedField(source="loft", queryset=Loft.objects.all())
    rollCode = serializers.CharField(source="roll_code")
    fabricWeightGsm = serializers.IntegerField(source="fabric_weight_gsm", required=False)
    loftName = serializers.CharField(source="loft.name", read_only=True)

    class Meta:
        model = ClothRoll
        fields = (
            "id",
            "loftId",
            "loftName",
            "rollCode",
            "status",
            "fabricWeightGsm",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "loftName", "created_at", "updated_at")

    def validate(self, attrs):
        loft = attrs.get("loft") or getattr(self.instance, "loft", None)
        roll_code = attrs.get("roll_code") or getattr(self.instance, "roll_code", None)
        if loft and roll_code:
            qs = ClothRoll.objects.filter(loft=loft, roll_code=roll_code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"rollCode": "同一帆布间卷号必须唯一"})

        new_status = attrs.get("status")
        if new_status == ClothRoll.STATUS_CURED:
            roll = self.instance
            if roll is None:
                raise serializers.ValidationError(
                    {"status": "新建布卷不能直接设为已固化"}
                )
            # 合并未提交字段到临时视角：用当前实例校验
            ok, msg = can_mark_roll_cured(roll)
            if not ok:
                raise serializers.ValidationError({"status": msg})
        return attrs


class DipRunSerializer(serializers.ModelSerializer):
    rollId = serializers.PrimaryKeyRelatedField(
        source="roll", queryset=ClothRoll.objects.all()
    )
    startedAt = serializers.DateTimeField(source="started_at")
    resinPct = serializers.DecimalField(source="resin_pct", max_digits=5, decimal_places=2)
    cureHours = serializers.DecimalField(
        source="cure_hours",
        max_digits=6,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    rollCode = serializers.CharField(source="roll.roll_code", read_only=True)
    loftName = serializers.CharField(source="roll.loft.name", read_only=True)

    class Meta:
        model = DipRun
        fields = (
            "id",
            "rollId",
            "rollCode",
            "loftName",
            "startedAt",
            "resinPct",
            "cureHours",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "rollCode", "loftName", "created_at")

    def validate(self, attrs):
        # 写入非空固化时长（新建带时长 / 补写 / 改写）时校验该间现行贴纸；
        # 登记新浸渍且时长留空不看贴纸。止日当天仍有效，过了止日中文挡住。
        if attrs.get("cure_hours") is not None:
            roll = attrs.get("roll") or getattr(self.instance, "roll", None)
            if roll is not None:
                msg = cure_hours_block_message(roll.loft)
                if msg:
                    raise serializers.ValidationError({"cureHours": msg})
        return attrs


class HygrometerStickerSerializer(serializers.ModelSerializer):
    loftId = serializers.PrimaryKeyRelatedField(source="loft", queryset=Loft.objects.all())
    loftName = serializers.CharField(source="loft.name", read_only=True)
    instrumentNo = serializers.CharField(source="instrument_no", max_length=60)
    stopDate = serializers.DateField(source="stop_date")
    pastedBy = serializers.CharField(source="pasted_by.username", read_only=True)
    voidedAt = serializers.DateTimeField(source="voided_at", read_only=True)
    isCurrent = serializers.SerializerMethodField()
    isExpired = serializers.SerializerMethodField()

    class Meta:
        model = HygrometerSticker
        fields = (
            "id",
            "loftId",
            "loftName",
            "instrumentNo",
            "stopDate",
            "pastedBy",
            "voidedAt",
            "isCurrent",
            "isExpired",
            "created_at",
        )
        read_only_fields = (
            "id",
            "loftName",
            "pastedBy",
            "voidedAt",
            "isCurrent",
            "isExpired",
            "created_at",
        )

    def get_isCurrent(self, obj):
        return obj.voided_at is None

    def get_isExpired(self, obj):
        return obj.stop_date < timezone.localdate()


class StickerRenewSerializer(serializers.Serializer):
    """续期入参：新止日必填，仪器编号可随贴随改。"""

    stopDate = serializers.DateField(source="stop_date")
    instrumentNo = serializers.CharField(
        source="instrument_no", max_length=60, required=False, allow_blank=False
    )
