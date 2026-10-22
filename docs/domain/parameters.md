# Simulation parameters

Owner: Leo (Data Lead). These feed `packages/sim/configs/dental_cs.yaml` (SG-09) and are tuned by
`sg sim calibrate`. Every value has a **source** (IFU, observation, supervisor, estimate, plan)
and a **confidence** (low, medium, high). Estimates are allowed if marked. Manufacturer IFUs
legally control equipment operation; replace estimates with IFU values when Leo has the models.

Status: first draft from the plan and SG-00. **Every row marked `estimate` needs Leo's check.**

## Equipment

| Parameter | Value | Source | Confidence |
| --- | --- | --- | --- |
| Washer-disinfectors | 2 | SG-00 (observation) | high |
| Washer cycle time | 45 min (range 30 to 60) | Plan §3.3, washer IFU to verify | medium |
| Washer load capacity | 8 instrument sets per load | estimate | low |
| Steam sterilizers | 2 | SG-00 (observation) | high |
| Sterilizer cycle, dynamic air removal, wrapped | 4 min exposure at 132°C + about 30 min conditioning, drying and cooling = about 45 min total | Plan §3.3 (CDC, AAMI ST79), sterilizer IFU to verify | medium |
| Sterilizer cycle, gravity, wrapped | 30 min exposure at 121°C + about 30 min drying = about 60 min | Plan §3.3 (CDC) | medium |
| Sterilizer load capacity | 10 cassettes or 1 MF tray + 4 cassettes, or about 60 pouches | estimate | low |
| Ultrasonic cleaner cycle | 10 min | estimate | low |

## Per-unit stage times (minutes per unit, triangular min / mode / max)

| Unit | Decontamination | Inspection and assembly | Packaging | Source | Confidence |
| --- | --- | --- | --- | --- | --- |
| Cassette | 2 / 3 / 5 | 3 / 5 / 8 | 1 / 2 / 3 | estimate | low |
| Peel pouch | 0.3 / 0.5 / 1 | 0.3 / 0.5 / 1 | 0.3 / 0.5 / 1 | estimate | low |
| MF surgical tray | 5 / 8 / 12 | 10 / 15 / 25 | 3 / 4 / 6 | estimate | low |
| Handpiece (incl. lubrication per IFU) | 2 / 3 / 4 | 2 / 3 / 5 | 0.5 / 1 / 1.5 | estimate | low |
| Returned unused item | re-enters decontamination like its type | | | Plan §3.1 | medium |

Total pickup-to-sterile time must land at about 2 to 2.5 hours (SG-00, observation, medium).

## Work generated

| Driver | Work units | Source | Confidence |
| --- | --- | --- | --- |
| Per regular patient | 1 cassette + 2 peel pouches; 0.3 handpieces | estimate | low |
| Per MF case | 1 MF tray + 3 peel pouches | estimate | low |
| Per student clinic session | 12 cassette sets issued; 25% typically returned unused | estimate | low |
| Regular patients per weekday | 248 to 442, mean about 366 (week 1: 392, 343, 442, 404, 248) | observation (Leo, week 1) | medium |
| MF cases per day | about 20 | SG-00 (observation) | medium |
| Emergency and intake | not in the counts above; 5 to 15 per day | estimate | low |

## Arrival timing

| Parameter | Value | Source | Confidence |
| --- | --- | --- | --- |
| Morning clinic block | 8:00 AM to 12:00 PM; dirty instruments arrive from about 9:00 AM | estimate | low |
| Afternoon clinic block | 1:00 PM to 5:00 PM; arrivals from about 2:00 PM | estimate | low |
| Pickup frequency | every 60 min from clinics | estimate | low |
| MF schedule | cases spread 8:00 AM to 3:00 PM, trays return about 1 h after each case | estimate | low |

## Staffing and overtime

| Parameter | Value | Source | Confidence |
| --- | --- | --- | --- |
| Morning operation | about 3 staff, 7:00 AM to 3:00 PM | SG-00 (observation) | high |
| Afternoon starts | 3 at about 11:00 AM, 1 at 1:00 PM, 2 at the regular afternoon start (assume 3:00 PM) | SG-00 (observation; 3 PM start to confirm) | medium |
| Afternoon shift length | 8 h | estimate | low |
| Outside support | about 2 staff until about 8:00 PM (start time to confirm) | SG-00 (observation) | medium |
| Overtime | voluntary; willing morning staff stay until about 8 to 9 PM | SG-00 (observation) | medium |
| Overtime hard cutoff | 9:00 PM | Plan §11 | medium |

## Events

| Parameter | Value | Source | Confidence |
| --- | --- | --- | --- |
| Equipment downtime | one washer or sterilizer down on about 5% of days, repair 1 to 4 h | estimate | low |
| Urgent requests jumping the queue | 2 to 5 per day | estimate | low |
| Biological indicator failure and recall | about 1 per year; reprocess the affected load's day | estimate (CDC weekly spore testing) | low |
| Carryover backlog at 7:00 AM | light most days; heavy after high-volume days | estimate | low |

## Academic calendar (this term)

| Event | Dates | Source | Confidence |
| --- | --- | --- | --- |
| Semester start | TO CONFIRM (Leo) | school calendar | n/a |
| Exam weeks | TO CONFIRM (Leo) | school calendar | n/a |
| Thanksgiving break | Nov 26 to 29, 2026 (assumed) | estimate | low |
| Winter break | from about Dec 18, 2026 | estimate | low |
