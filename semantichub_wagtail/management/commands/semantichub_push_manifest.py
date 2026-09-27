from django.core.management.base import BaseCommand, CommandError

from semantichub_wagtail.manifest import is_configured, push_manifest


class Command(BaseCommand):
    help = (
        "Report this installation's capability manifest to SemanticHub "
        "(PUT /api/goals/{id}/target-manifest). Run once a day "
        "(host cron or a systemd timer) and right after changing get_fields()."
    )

    def handle(self, *args, **options):
        if not is_configured():
            raise CommandError(
                "SEMANTICHUB_API_BASE_URL, SEMANTICHUB_AGENT_TOKEN and "
                "SEMANTICHUB_GOAL_ID must be set"
            )
        if not push_manifest():
            raise CommandError("manifest push failed, see logs")
        self.stdout.write(self.style.SUCCESS("semantichub manifest pushed"))
