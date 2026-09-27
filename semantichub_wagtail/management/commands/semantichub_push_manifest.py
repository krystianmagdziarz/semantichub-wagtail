from django.core.management.base import BaseCommand, CommandError

from semantichub_wagtail.manifest import is_configured, push_manifest


class Command(BaseCommand):
    help = (
        "Zamelduj manifest zdolności tej instalacji w SemanticHubie "
        "(PUT /api/goals/{id}/target-manifest). Uruchamiaj raz na dobę "
        "(cron hosta albo systemd timer) i zaraz po zmianie get_fields()."
    )

    def handle(self, *args, **options):
        if not is_configured():
            raise CommandError(
                "SEMANTICHUB_API_BASE_URL, SEMANTICHUB_AGENT_TOKEN i "
                "SEMANTICHUB_GOAL_ID muszą być ustawione"
            )
        if not push_manifest():
            raise CommandError("manifest push failed, see logs")
        self.stdout.write(self.style.SUCCESS("semantichub manifest pushed"))
