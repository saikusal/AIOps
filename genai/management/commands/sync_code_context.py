from django.core.management.base import BaseCommand

from genai.code_context_ingestion import sync_all_active_repositories, sync_repository_index
from genai.models import RepositoryIndex


class Command(BaseCommand):
    help = "Sync local code-context indexes for all active repositories or a single named repository."

    def add_arguments(self, parser):
        parser.add_argument("--repository", dest="repository", default="", help="RepositoryIndex.name to sync")
        parser.add_argument("--recent-commits", dest="recent_commits", type=int, default=25, help="Number of local git commits to ingest")

    def handle(self, *args, **options):
        repository_name = (options.get("repository") or "").strip()
        recent_commits = int(options.get("recent_commits") or 25)
        if repository_name:
            repository = RepositoryIndex.objects.filter(name=repository_name).first()
            if not repository:
                self.stderr.write(self.style.ERROR(f"RepositoryIndex '{repository_name}' not found."))
                return
            result = sync_repository_index(repository, recent_commit_limit=recent_commits)
            self.stdout.write(self.style.SUCCESS(f"Synced {repository.name}: {result}"))
            return

        results = sync_all_active_repositories(recent_commit_limit=recent_commits)
        self.stdout.write(self.style.SUCCESS(f"Synced {len(results)} repository index job(s)."))
        for item in results:
            self.stdout.write(str(item))
