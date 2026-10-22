# Data access and approvals

Owner: Leo (Data Lead). Records every request for real data, its status and dates. Real data is
stored only in Supabase with `source = 'real'`; it is never committed to this repository.

## Status

| Request | To | Sent | Status | Notes |
| --- | --- | --- | --- | --- |
| Anonymous daily logging (template attached) | Department supervisor | not yet | **pending: Leo to send** | Draft below |
| Aggregate Kronos overtime, morning operation, daily totals, no names or IDs | Department supervisor (forward to timekeeping) | not yet | **pending: Leo to send** | Draft below |

Update this table with dates and replies. Store any written approval outside the repo (team drive)
and note here only that it exists.

## Where the real data lives

- Week 1 (Mon to Fri, regular patients 392, 343, 442, 404, 248, plus staff and overtime from
  Leo's records): filled into `daily-log-template.xlsx` and kept **only** on the private team
  drive or Leo's laptop. Loaded into Supabase as `source = 'real'` by the SG-20 backfill form or
  the SG-21 import, whichever lands first.
- Daily logs from Oct 12 to at least Nov 20 (the threshold freeze date, SG-29): same template,
  same private location, imported weekly.
- `.gitignore` blocks `data/**` and any file with `real` or `week` in its name under
  `docs/domain/`, as a guard against accidental commits.

## Draft: anonymous daily logging request

> Subject: Request to log anonymous daily workload counts for a Stevens course project
>
> Hello [supervisor],
>
> For my CPE 595 Applied Machine Learning project at Stevens, our team is building a decision
> support prototype that forecasts next-day overtime for the morning operation of Dental Central
> Sterile. I would like to record a few anonymous counts each workday until about November 20:
> scheduled regular patients, MF cases, staff present by start time, equipment status, and total
> overtime hours for the morning operation.
>
> The log contains no patient information and no employee names or IDs, only daily counts and
> totals. A blank copy of the log is attached. The data stays in a private, access-controlled
> project database, is used only for the course project, and is deleted at the end of the term
> on request. The tool is an academic prototype and will not be used to evaluate any individual.
>
> May I start logging? I'm happy to adjust what is collected.
>
> Thank you,
> Leo

## Draft: aggregate Kronos overtime request

> Subject: Request for aggregate daily overtime totals (no names or IDs)
>
> Hello [supervisor],
>
> As part of the same course project, would it be possible to receive the **daily total**
> overtime hours for the Dental Central Sterile morning operation (7:00 AM to 3:00 PM staff) from
> Kronos for this semester? We only need one number per day, with no employee names, IDs, or
> individual hours. Outside-department support should be excluded.
>
> The totals would be used in aggregate to check our forecasts and would be stored privately.
>
> Thank you,
> Leo
