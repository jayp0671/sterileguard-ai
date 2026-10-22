---
name: sterile-processing-domain
description: Sterile processing domain reference for SterileGuard AI (reprocessing workflow, work units, timings, quality monitoring, standards, workload drivers, and the Dental Central Sterile facts the code must respect). Use when writing simulation, features, data schema, or user-facing copy.
---

# Sterile processing domain

## Facts the code must respect (SG-00)

- Morning operation: about 3 employees, 7:00 AM to 3:00 PM. The prediction target is overtime of
  this operation only.
- Staggered afternoon coverage is a staffing input, not predicted: 3 start about 11:00 AM, 1 at
  1:00 PM, 2 at the regular afternoon start (assume 3:00 PM until Leo confirms).
- About 2 outside-department staff support until about 8:00 PM. Capacity, not overtime.
- Overtime is voluntary. Willing morning staff stay until about 8 to 9 PM. "Staff willing to
  stay" is a separate input from headcount.
- 2 washers, 2 sterilizers. Pickup to sterile takes about 2 to 2.5 hours.
- Regular patients per weekday 248 to 442 (mean about 366; week 1: 392, 343, 442, 404, 248).
  About 20 MF cases per day. Emergency and intake patients are not in those counts.
- Returned unused instruments are a major hidden load, known only after the shift. Never a
  pre-shift input. Scheduled student clinic sessions are the pre-shift proxy.
- Overtime labor-hours = total hours past the scheduled end worked by morning Dental Central
  Sterile employees (outside support excluded).
- Burden categories: provisional cutoffs from the calibrated simulation; final from real-data
  terciles, frozen by Nov 20 in an ADR.
- Data tiers: Tier 1 required daily; Tier 2 context with defaults plus `__missing` flags;
  Tier 3 after-shift analysis only, never model inputs.

## Plan §3 reference

This is the sterile processing knowledge the simulation and features are built on. Leo should verify every number against the department's procedures and the manufacturers' instructions for use (IFUs), which legally control how equipment is operated.
 
### 1 Reprocessing workflow
 
1. **Point of use.** Clinicians pre-clean and contain used instruments in the clinic.
2. **Transport** to Central Sterile in closed, labeled containers.
3. **Receiving and decontamination.** Staff in PPE sort, disassemble, and soak items (OSHA Bloodborne Pathogens Standard applies).
4. **Cleaning** in ultrasonic cleaners and washer-disinfectors. The department has two washers.
5. **Inspection and assembly.** Check cleanliness and function, often under magnification. Handpieces are lubricated per IFU.
6. **Packaging.** Cassettes are wrapped, single instruments go in peel pouches, each with a chemical indicator.
7. **Sterilization** in steam sterilizers. The department has two.
8. **Cooling, drying, and storage.**
9. **Distribution** to clinics, student modules, and maxillofacial (MF) surgery.
10. **Returns.** Issued but unused instruments come back and re-enter the workflow.
### 2 Instrument categories and work units
 
The Spaulding classification drives handling. Critical items that penetrate tissue (surgical instruments, scalers, burs) must be heat sterilized. Semicritical items that touch mucous membranes (mirrors, handpieces) are heat sterilized when heat tolerant. Noncritical items get cleaning and disinfection.
 
| Work unit | Examples | Modeling notes |
| --- | --- | --- |
| Cassette | Exam, restorative, and periodontal kits | Most common unit from student clinics |
| Peel pouch | Single instruments, burs, endodontic files | High volume, short per-unit time |
| MF surgical tray | Maxillofacial sets | Larger, longer inspection and assembly |
| Handpiece | High and low speed | Cleaning, lubrication, and sterilization per IFU |
| Returned unused item | Any issued item not used | Re-enters decontamination |
 
### 3 Timing starting points for calibration
 
| Stage | Typical value | Verify against |
| --- | --- | --- |
| Washer-disinfector cycle | About 30 to 60 minutes | Washer IFU |
| Steam, dynamic air removal, wrapped | 132°C (270°F) for 4 minutes exposure, plus drying | CDC, AAMI ST79, sterilizer IFU |
| Steam, gravity displacement, wrapped | 121°C (250°F) for 30 minutes exposure, plus drying | CDC, sterilizer IFU |
| Pickup to sterile, full workflow | 2 to 2.5 hours | Leo's observations |
 
### 4 Quality monitoring
 
Every cycle is monitored mechanically (cycle printouts), every package carries a chemical indicator, and CDC recommends biological spore testing at least weekly in dental settings. A failed biological indicator triggers a recall and a reprocessing spike, which the simulation models as a rare event.
 
### 5 Governing standards
 
- CDC Guidelines for Infection Control in Dental Health-Care Settings (2003) and the Summary of Infection Prevention Practices in Dental Settings (2016)
- ANSI/AAMI ST79, comprehensive guide to steam sterilization in health care facilities
- OSHA Bloodborne Pathogens Standard, 29 CFR 1910.1030
- Manufacturer IFUs for every washer, sterilizer, and instrument
### 6 Workload drivers
 
- **Known before 7 AM (model inputs):** scheduled patients, MF cases, student clinic sessions, academic calendar (exams, breaks, semester start), staffing by time window, voluntary overtime availability, outside support, washer and sterilizer status, carryover backlog, day of week, holidays
- **Known after the shift (calibration and analysis):** returned unused instruments, emergency and intake volume, equipment downtime, biological indicator failures, end-of-day backlog
