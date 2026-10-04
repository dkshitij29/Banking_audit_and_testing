Write the prose of a discharge summary for this admission.

THE ADMISSION
$facts

TOKENS YOU MAY USE
$tokens

WRITE THESE FIELDS

- `presenting_complaint` — why the patient came in, in the words a doctor would
  use on admission. One or two sentences.
- `history` — the relevant background: how long the trouble had been going on
  (qualitatively), what was tried before coming in, and any long-standing
  conditions listed above. One or two sentences. Say "no significant past
  history" if there is nothing to report.
- `examination` — what was found on examination at admission: general
  condition, the relevant system, and the state of the affected part. Two or
  three sentences, no vital signs (they would need numbers).
- `course_in_hospital` — what was done and how the patient responded, in order:
  assessment, treatment or operation, recovery. Name the operation with its
  token where there was one. Three or four sentences.
- `condition_at_discharge` — how the patient was on the day of discharge:
  symptoms settled, wound healthy, walking, taking food. One or two sentences.
- `advice_on_discharge` — what the patient was told to do at home: medicines as
  prescribed, wound care, diet and activity, when to come back, and what should
  bring them back sooner. Two or three sentences. Refer to medicines by kind,
  never by name or dose.

Do not add a side (left, right, both), a stage, a grade or a severity that is
not already in the diagnosis above. Do not name a second illness the record does
not list.

$correction
