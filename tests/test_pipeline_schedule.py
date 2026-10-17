import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from core.scheduling import is_due
from snapshots.orchestrators.snapshot_scheduler import should_create_snapshot_job
from normalized.orchestrators import normalization_scheduler
from metrics.builders.orchestrators import metric_scheduler

class PipelineScheduleTests(unittest.TestCase):
    def test_daily_run_uses_next_utc_date_not_finish_time(self):
        last=datetime(2026,10,17,6,30,tzinfo=timezone.utc)
        self.assertTrue(is_due(last,24,datetime(2026,10,18,0,30,tzinfo=timezone.utc)))
        self.assertFalse(is_due(last,24,datetime(2026,10,17,23,59,tzinfo=timezone.utc)))

    def test_subdaily_and_multiday_keep_elapsed_intervals(self):
        last=datetime(2026,10,17,23,30,tzinfo=timezone.utc)
        self.assertFalse(is_due(last,1,datetime(2026,10,18,0,0,tzinfo=timezone.utc)))
        self.assertTrue(is_due(last,1,datetime(2026,10,18,0,30,tzinfo=timezone.utc)))
        self.assertFalse(is_due(last,48,datetime(2026,10,19,0,30,tzinfo=timezone.utc)))

    def test_all_stage_schedulers_share_the_policy(self):
        state=dict(status='success',last_success_at='2026-10-17T06:30:00+00:00')
        now=datetime(2026,10,18,0,30,tzinfo=timezone.utc)
        with patch('snapshots.orchestrators.snapshot_scheduler.utc_now',return_value=now):
            self.assertTrue(should_create_snapshot_job(state=state,registry_entry=dict(run_frequency_hours=24)))
        for module,fn in [(normalization_scheduler,normalization_scheduler.should_create_normalization_job),(metric_scheduler,metric_scheduler.should_create_metric_job)]:
            with patch.object(module,'datetime',wraps=datetime) as clock:
                clock.now.return_value=now
                self.assertTrue(fn(state,dict(run_frequency_hours=24)))
