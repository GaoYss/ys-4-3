from django.db import migrations


def fix_duplicate_active_versions(apps, schema_editor):
    FeeType = apps.get_model("communities", "FeeType")
    fee_names = list(
        FeeType.objects.values_list("name", flat=True).distinct()
    )
    for name in fee_names:
        active_versions = FeeType.objects.filter(name=name, is_active=True).order_by(
            "-effective_date", "-version"
        )
        if active_versions.count() > 1:
            ids_to_deactivate = list(
                active_versions.values_list("id", flat=True)[1:]
            )
            FeeType.objects.filter(id__in=ids_to_deactivate).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("communities", "0003_alter_feetype_options_alter_feetype_version_and_more"),
    ]

    operations = [
        migrations.RunPython(fix_duplicate_active_versions),
    ]
