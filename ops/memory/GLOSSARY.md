# Glossary

| Term | Meaning |
| --- | --- |
| Cassette | A closed tray holding a kit (exam, restorative, perio). Most common work unit from student clinics |
| Peel pouch | Sealed pouch for single instruments, burs, endo files. High volume, short per-unit time |
| MF tray | Maxillofacial surgical set. Larger, longer inspection and assembly |
| Handpiece | High- or low-speed dental drill. Cleaned, lubricated and sterilized per IFU |
| IFU | Manufacturer's Instructions for Use. Legally controls how equipment and instruments are processed |
| BI | Biological indicator (spore test). A failure triggers a recall and a reprocessing spike |
| Carryover backlog | Unfinished work at the end of a day that is waiting at 7:00 AM the next day |
| Overtime availability | Number of morning staff who agreed to stay past 3:00 PM. Overtime is voluntary |
| Outside support | About 2 staff from outside the department who help until about 8:00 PM. Capacity, not overtime |
| Overtime labor-hours | Total hours past the scheduled end worked by morning Dental Central Sterile staff (outside support excluded). The prediction target |
| Tier 1 | Required daily fields: date, regular patients, morning staff present, overtime labor-hours |
| Tier 2 | Context fields logged when known (MF cases, clinic sessions, afternoon staffing, outside support, staff willing to stay, equipment up, carryover). Missing values use department defaults plus a `__missing` flag |
| Tier 3 | After-shift fields for analysis only (emergency/intake patients, returned unused estimate, downtime, notes). Never model inputs |
| Burden category | Low / medium / high overtime class. Provisional cutoffs from simulation, final from real-data terciles frozen by Nov 20 |
| Returned unused | Issued instruments that come back unused and must be reprocessed. Known only after the shift |
| aal1 / aal2 | Supabase authenticator assurance level. aal2 means two-factor completed; RLS requires it |
