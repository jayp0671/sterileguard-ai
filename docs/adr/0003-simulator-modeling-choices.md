# 0003. Simulator modeling choices

- Status: proposed (needs Leo's review)
- Date: 2026-10-22
- Deciders: Jay, Leo
- Ticket: SG-09

## Context and problem statement

SG-09 asks for a SimPy model where overtime emerges from workload against capacity. Several
details were left open or did not fit the first-draft parameters in
`docs/domain/parameters.md`, and the model has to run before any real days exist.

## Considered options

1. Staff as a `simpy.Resource` whose capacity a controller process changes over time.
2. Staff as one SimPy process per person that pulls work from priority queues.

## Decision outcome

Chosen option: 2, one process per person. Shift starts and ends, the 15:00 stay-or-leave
decision, per-person overtime, and "nobody works outside their presence" all become exact.
A resource with changing capacity cannot remove a token that is in use, so it needs extra
bookkeeping to stop someone working past their shift.

Other choices:

- **No task crosses a person's end time.** A worker never starts a task they cannot finish
  before leaving. Morning stayers are the exception before 15:00. Stayers re-decide at every
  task boundary after 15:00, and re-check every 10 minutes while idle.
- **Machine loads are counted in load units.** A pouch is lighter than a cassette, so
  capacity counts load units instead of units (`units.*.weight`). A machine waits up to
  `max_load_wait` minutes for a fuller load.
- **Machine capacity and stage times differ from the first-draft parameters.** With the
  draft values (washer 8 sets, sterilizer about 10 cassettes, full stage times), two
  machines would need about 19 hours a day and the backlog grows without limit. Washer and
  sterilizer capacity are raised to 40 load units. `scale.stage_time` starts at 0.55, so a
  normal day roughly clears and the backlog stays stationary. Both values are estimates for
  Leo to replace with IFU values and real days. Calibration then re-tunes `stage_time`.
- **Stay threshold.** `ot_stay_threshold` is 30 units in progress per staff member. This
  gives a mean stayer leave time of about 20:00, inside the 20:00 to 21:00 window. Overtime
  correlates about 0.8 with patients.
- **Carryover keeps its stage.** Units in progress at 23:00 resume next day at the stage
  they reached, so a packaged set is not decontaminated again. Fresh backlog from the 0-2
  scale waits at decontamination.
- **Carryover is capped between days.** Carryover passed to the next day is capped at
  `work.max_carryover_units` (400). The LHS design includes weak staffing (2 morning staff,
  1 washer), where the backlog would otherwise grow without limit. A real department would
  call in surge help, which the model does not include. Conservation still holds within
  each day.
- **Simulated dates are unique.** The 5,000-day dataset is laid out as 250 sequences of
  20 workdays, 28 days apart from 2007, so every date is unique under
  `unique (department_id, date, source)`. A new simulated dataset replaces the
  department's previous one.
- **Direct database connection for uploads.** `sg sim run --env` uploads through a direct
  postgres connection, which bypasses RLS like the service role. The URL comes from the
  `sg db` guards, which allow local and staging and refuse prod.

### Consequences

- Good: invariants (conservation, capacity, presence, downtime) are easy to assert.
- Bad: the parameters are estimates until Leo confirms them. With no real days, calibration
  only checks plausibility, so the MAE acceptance criterion waits for real data.

## Links

- Plan section: §3, §10.0, §11
- `packages/sim/configs/dental_cs.yaml`, `packages/sim/src/sg_sim/model.py`
