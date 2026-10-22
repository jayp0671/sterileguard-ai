# Data dictionary

Owner: Leo (Data Lead). Plan §10.0. Column names match `daily-log-template.csv` exactly; SG-08
codifies them in `packages/data/schema.py`. **Never record patient or employee names or IDs.**

Status legend: **TO CONFIRM (Leo)** marks an answer only Leo can give from the department. The
proposed default is what the code assumes until he confirms.

## The five open questions (plan §10.0)

| # | Question | Answer | Status |
| --- | --- | --- | --- |
| 1 | Is "employees" the number scheduled or actually present, and morning only or the whole department? | Proposed: **actually present**, **morning operation only** (7:00 AM to 3:00 PM), Dental Central Sterile staff only. That is `morning_staff_present`. Afternoon starts are logged separately in `aft_11_staff`, `aft_13_staff`, `aft_15_staff`. | TO CONFIRM (Leo) |
| 2 | Is overtime the combined hours of all morning staff, and is the source Kronos, a supervisor, or direct observation? | Proposed: **combined** decimal hours of all morning DCS staff past 3:00 PM (3 people staying 5 h = 15). Outside support excluded. Source for week 1: Leo's direct observation; later Kronos daily aggregates if approved (see data-access.md). Record the source per day in `notes` until a `source_detail` column exists. | TO CONFIRM (Leo) |
| 3 | Which Tier 2 fields can realistically be logged every day? | Proposed daily: `mf_cases`, `aft_11_staff`, `aft_13_staff`, `aft_15_staff`, `outside_support_staff`, `ot_available_staff`, `washers_up`, `sterilizers_up`, `is_holiday`, `academic_event`. Best effort: `student_clinic_sessions`, `carryover_backlog_estimate`. Missing Tier 2 values are filled from department defaults with a `__missing` flag, never invented. | TO CONFIRM (Leo) |
| 4 | Does the department operate on weekends? | Proposed: **no**, Monday to Friday only (the observed week was Mon to Fri). Weekend rows are not expected; if they occur, log them like any other day. | TO CONFIRM (Leo) |
| 5 | Which unit for carryover backlog? | Proposed: a **3-point scale** `0 = light, 1 = normal, 2 = heavy`, judged at 7:00 AM. Easier to log consistently than counting carts or trays. Switch to a count only if the department already counts carts. | TO CONFIRM (Leo) |

## Fields

Tier 1 rows missing any required field are rejected. "When" is relative to the 7:00 AM start.

| Column | Tier | Definition | Unit | How measured | Who records | When |
| --- | --- | --- | --- | --- | --- | --- |
| `date` | 1 | Calendar date of the shift | YYYY-MM-DD | Calendar | Leo | Before |
| `regular_patients` | 1 | Scheduled regular patients (emergency and intake excluded) | patients | Clinic schedule count | Leo | Before |
| `morning_staff_present` | 1 | DCS staff present for the morning operation | people | Head count at 7:00 AM | Leo | Before |
| `ot_labor_hours` | 1 | Hours past scheduled end, summed over morning DCS staff | decimal hours | Clock-out times minus 3:00 PM, summed | Leo (later Kronos) | After |
| `mf_cases` | 2 | Maxillofacial surgery cases scheduled (about 20) | cases | MF schedule | Leo | Before |
| `student_clinic_sessions` | 2 | Scheduled student clinic sessions | sessions | Clinic schedule | Leo | Before |
| `aft_11_staff` | 2 | Staff starting about 11:00 AM (default 3) | people | Schedule | Leo | Before |
| `aft_13_staff` | 2 | Staff starting about 1:00 PM (default 1) | people | Schedule | Leo | Before |
| `aft_15_staff` | 2 | Staff starting at the regular afternoon start (default 2) | people | Schedule | Leo | Before |
| `outside_support_staff` | 2 | Outside-department helpers (default 2, until about 8 PM) | people | Schedule | Leo | Before |
| `ot_available_staff` | 2 | Morning staff who agreed to stay | people | Ask at start of shift | Leo | Before |
| `washers_up` | 2 | Washer-disinfectors working | 0 to 2 | Check at 7:00 AM | Leo | Before |
| `sterilizers_up` | 2 | Sterilizers working | 0 to 2 | Check at 7:00 AM | Leo | Before |
| `carryover_backlog_estimate` | 2 | Work waiting at 7:00 AM | 0, 1, 2 (proposed) | Visual judgment | Leo | Before |
| `is_holiday` | 2 | Holiday or school closed | 0 or 1 | Calendar | Leo | Before |
| `academic_event` | 2 | none, exam, break, semester_start | category | Academic calendar | Leo | Before |
| `emergency_intake_patients` | 3 | Emergency and intake patients | patients | End-of-day count | Leo | After |
| `returned_unused_estimate` | 3 | Issued but unused sets returned | sets | End-of-day estimate | Leo | After |
| `equipment_downtime_minutes` | 3 | Washer and sterilizer downtime | minutes | Cycle logs or observation | Leo | After |
| `notes` | 3 | Short operational notes, never names | text | Free text | Leo | After |

Tier 3 fields are for calibration and analysis only and are never model inputs (feature registry,
SG-13).
