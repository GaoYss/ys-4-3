import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def set_default_fee_type_values(apps, schema_editor):
    FeeType = apps.get_model("communities", "FeeType")
    FeeType.objects.filter(version__isnull=True).update(
        version=1,
        effective_date=timezone.localdate(),
        created_at=timezone.now(),
    )


def set_default_bill_snapshot(apps, schema_editor):
    Bill = apps.get_model("communities", "Bill")
    for bill in Bill.objects.select_related("fee_type").all():
        fee_type = bill.fee_type
        snapshot = {
            "id": fee_type.id,
            "name": fee_type.name,
            "version": 1,
            "version_label": f"v1 ({timezone.localdate().strftime('%Y-%m-%d')}起生效)",
            "effective_date": timezone.localdate().isoformat(),
            "billing_method": fee_type.billing_method,
            "billing_method_label": dict(fee_type._meta.get_field("billing_method").flatchoices)[fee_type.billing_method],
            "amount": str(fee_type.amount),
            "cycle": fee_type.cycle,
            "cycle_label": dict(fee_type._meta.get_field("cycle").flatchoices)[fee_type.cycle],
            "description": fee_type.description,
        }
        bill.fee_type_snapshot = snapshot
        bill.save(update_fields=["fee_type_snapshot"])


class Migration(migrations.Migration):

    dependencies = [
        ("communities", "0001_initial"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="feetype",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="feetype",
            name="name",
            field=models.CharField(max_length=80, verbose_name="费用名称"),
        ),
        migrations.AddField(
            model_name="feetype",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="versions",
                to="communities.feetype",
                verbose_name="主费用类型",
            ),
        ),
        migrations.AddField(
            model_name="feetype",
            name="version",
            field=models.PositiveIntegerField(
                default=1,
                verbose_name="版本号",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="feetype",
            name="effective_date",
            field=models.DateField(
                default=timezone.localdate,
                verbose_name="生效日期",
            ),
        ),
        migrations.AddField(
            model_name="feetype",
            name="created_at",
            field=models.DateTimeField(
                default=timezone.now,
                verbose_name="创建时间",
            ),
        ),
        migrations.AddField(
            model_name="bill",
            name="fee_type_snapshot",
            field=models.JSONField(
                default=dict,
                verbose_name="费用标准快照",
            ),
        ),
        migrations.RunPython(set_default_fee_type_values),
        migrations.RunPython(set_default_bill_snapshot),
        migrations.AlterUniqueTogether(
            name="feetype",
            unique_together={("name", "version")},
        ),
    ]
