-- Local and staging only. Never run against prod. Synthetic demo tenancy, no users
-- (SG-16 creates demo users). Fixed UUIDs so tests and fixtures can refer to them.

insert into public.organizations (id, name, allowed_email_domains)
values ('00000000-0000-4000-8000-000000000001', 'Demo Health System', '{}')
on conflict (id) do nothing;

insert into public.facilities (id, organization_id, name, timezone)
values (
  '00000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000001',
  'Demo Dental School',
  'America/New_York'
)
on conflict (id) do nothing;

insert into public.departments (id, facility_id, name, slug, settings)
values (
  '00000000-0000-4000-8000-000000000003',
  '00000000-0000-4000-8000-000000000002',
  'Dental Central Sterile',
  'dental-cs',
  '{
    "shift_windows": [
      {"key": "morning", "start": "07:00", "end": "15:00", "default_staff": 3},
      {"key": "aft_11", "start": "11:00", "end": "19:00", "default_staff": 3},
      {"key": "aft_13", "start": "13:00", "end": "21:00", "default_staff": 1},
      {"key": "aft_15", "start": "15:00", "end": "23:00", "default_staff": 2}
    ],
    "outside_support_default": 2,
    "outside_support_until": "20:00",
    "washers": 2,
    "sterilizers": 2,
    "mf_cases_default": 20,
    "burden_thresholds": null,
    "alert_threshold_hours": null,
    "retention_days_drafts": 90
  }'::jsonb
)
on conflict (id) do nothing;
