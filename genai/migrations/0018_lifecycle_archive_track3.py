# Generated for Track 3.4 and 3.5 — Lifecycle jobs, retention holds, archive manifests, evidence artifacts

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('genai', '0017_alter_dataretentionpolicy_options_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------ #
        # Track 3.4 — LifecycleJobRun                                        #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='LifecycleJobRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_run_id', models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ('job_type', models.CharField(
                    choices=[
                        ('prune_expired_caches', 'Prune Expired Caches'),
                        ('prune_stale_snapshots', 'Prune Stale Snapshots'),
                        ('prune_tool_response_raw', 'Prune Raw Tool Responses'),
                        ('archive_evidence_bundles', 'Archive Evidence Bundles'),
                        ('compact_investigation_runs', 'Compact Investigation Runs'),
                        ('rotate_heartbeat_snapshots', 'Rotate Heartbeat Snapshots'),
                        ('expire_enrollment_tokens', 'Expire Enrollment Tokens'),
                        ('prune_replay_scenarios', 'Prune Replay Scenarios'),
                        ('custom', 'Custom'),
                    ],
                    default='custom',
                    max_length=64,
                )),
                ('status', models.CharField(
                    choices=[
                        ('running', 'Running'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                        ('skipped', 'Skipped'),
                    ],
                    default='running',
                    max_length=16,
                )),
                ('triggered_by', models.CharField(blank=True, default='cron', max_length=64)),
                ('records_scanned', models.PositiveIntegerField(default=0)),
                ('records_pruned', models.PositiveIntegerField(default=0)),
                ('records_archived', models.PositiveIntegerField(default=0)),
                ('records_skipped', models.PositiveIntegerField(default=0)),
                ('job_params_json', models.JSONField(blank=True, default=dict)),
                ('result_summary_json', models.JSONField(blank=True, default=dict)),
                ('error_detail', models.TextField(blank=True, default='')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('duration_seconds', models.FloatField(blank=True, null=True)),
            ],
            options={'ordering': ['-started_at']},
        ),

        # ------------------------------------------------------------------ #
        # Track 3.4 — RetentionHold                                          #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='RetentionHold',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hold_id', models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ('evidence_bundle', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='retention_holds',
                    to='genai.evidencebundle',
                )),
                ('incident', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='retention_holds',
                    to='genai.incident',
                )),
                ('investigation_run', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='retention_holds',
                    to='genai.investigationrun',
                )),
                ('hold_reason', models.CharField(
                    choices=[
                        ('legal', 'Legal Hold'),
                        ('regulatory', 'Regulatory Compliance'),
                        ('severity', 'High Severity Incident'),
                        ('operator', 'Operator Manual Hold'),
                        ('audit', 'Audit Request'),
                    ],
                    default='operator',
                    max_length=32,
                )),
                ('description', models.TextField(blank=True, default='')),
                ('held_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='aiops_retention_holds',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('metadata_json', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('released_at', models.DateTimeField(blank=True, null=True)),
                ('released_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='aiops_released_retention_holds',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),

        # ------------------------------------------------------------------ #
        # Track 3.5 — ArchiveManifest                                        #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='ArchiveManifest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('manifest_id', models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ('evidence_bundle', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='archive_manifest',
                    to='genai.evidencebundle',
                )),
                ('archive_backend', models.CharField(
                    choices=[
                        ('minio', 'MinIO (local object storage)'),
                        ('s3', 'AWS S3'),
                        ('gcs', 'Google Cloud Storage'),
                        ('azure_blob', 'Azure Blob Storage'),
                        ('local_fs', 'Local Filesystem (dev/test)'),
                    ],
                    default='minio',
                    max_length=32,
                )),
                ('bucket_name', models.CharField(blank=True, default='', max_length=255)),
                ('object_key', models.CharField(blank=True, default='', max_length=1024)),
                ('object_url', models.CharField(blank=True, default='', max_length=2048)),
                ('content_type', models.CharField(default='application/json', max_length=128)),
                ('size_bytes', models.BigIntegerField(default=0)),
                ('checksum_sha256', models.CharField(blank=True, default='', max_length=64)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending Upload'),
                        ('uploaded', 'Uploaded'),
                        ('verified', 'Verified'),
                        ('failed', 'Failed'),
                        ('deleted', 'Deleted'),
                    ],
                    default='pending',
                    max_length=16,
                )),
                ('manifest_json', models.JSONField(blank=True, default=dict)),
                ('includes_snapshots', models.BooleanField(default=True)),
                ('includes_transcripts', models.BooleanField(default=True)),
                ('includes_tool_responses', models.BooleanField(default=False)),
                ('uploaded_at', models.DateTimeField(blank=True, null=True)),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),

        # ------------------------------------------------------------------ #
        # Track 3.5 — EvidenceArtifact                                       #
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='EvidenceArtifact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('artifact_id', models.CharField(db_index=True, default=uuid.uuid4, max_length=64, unique=True)),
                ('evidence_bundle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='artifacts',
                    to='genai.evidencebundle',
                )),
                ('investigation_run', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='evidence_artifacts',
                    to='genai.investigationrun',
                )),
                ('tool_invocation', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='evidence_artifacts',
                    to='genai.toolinvocation',
                )),
                ('artifact_type', models.CharField(
                    choices=[
                        ('tool_response', 'Tool Response Payload'),
                        ('log_excerpt', 'Log Excerpt'),
                        ('trace_excerpt', 'Trace Excerpt'),
                        ('metrics_snapshot', 'Metrics Snapshot'),
                        ('code_snippet', 'Code Snippet'),
                        ('llm_prompt', 'LLM Prompt'),
                        ('llm_response', 'LLM Response'),
                        ('runbook_content', 'Runbook Content'),
                        ('other', 'Other'),
                    ],
                    default='other',
                    max_length=32,
                )),
                ('storage_backend', models.CharField(
                    choices=[
                        ('postgres_json', 'Postgres JSON (inline)'),
                        ('object_storage', 'Object Storage'),
                        ('local_fs', 'Local Filesystem (dev/test)'),
                    ],
                    default='postgres_json',
                    max_length=32,
                )),
                ('content_json', models.JSONField(blank=True, default=dict)),
                ('object_key', models.CharField(blank=True, default='', max_length=1024)),
                ('size_bytes', models.BigIntegerField(default=0)),
                ('is_pruned', models.BooleanField(default=False)),
                ('pruned_at', models.DateTimeField(blank=True, null=True)),
                ('metadata_json', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
