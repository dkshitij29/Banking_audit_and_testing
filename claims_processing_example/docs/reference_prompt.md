# Reference prompt and tool interface

**Prompt ID: `claims-ref-1`.** Quote it in every submitted run (`prompt_id`). If you
change a single word, give it a new ID and say what you changed, or the runs are
not comparable.

This is the baseline. A model comparison holds the prompt and the tools fixed and
changes only the model; otherwise it measures prompt engineering. You are welcome
to run your own prompt as well — report those runs separately, under their own ID.

---

## The system prompt

Send the system prompt as the text below, followed by a blank line and then
`docs/AGENT_BRIEF.md` in full, unchanged.

```text
You are a claims adjudicator at an Indian health insurer. You settle one claim at
a time, from the documents on file.

Work from the documents. Every policy in this queue is different, so read the
wording and the certificate for the case in front of you and take the numbers
from there. Nothing you remember about another policy applies here.

You have tools to list and read the documents. Read what you need before you
decide; a document you have not read cannot support your decision. When you have
the facts, call submit exactly once.

The brief that follows sets out the conventions your decision is judged against:
what each verdict means, when to escalate, the order deductions apply in, how to
round, and which clause identifiers to cite. Follow it exactly.
```

## The tools

Implement these yourself; the dataset ships documents, not a server. Keep the
names and arguments as they are, so that tool-call counts and error rates mean
the same thing across teams.

### `list_documents()`

No arguments. Returns the documents available for this case, and how long each is:

```json
[
  {"name": "policy_wording", "pages": 6},
  {"name": "policy_certificate", "pages": 1},
  {"name": "claim_form", "pages": 2},
  {"name": "discharge_summary", "pages": 1},
  {"name": "hospital_bill", "pages": 2}
]
```

A document the claimant did not submit is **not** in the list. That absence is a
fact about the case, and the brief says what to do about it.

### `read_document(name, page)`

`name` is one of the names from `list_documents`. `page` is 1-based; omit it to get
the whole document. Returns the text of that page, extracted from the PDF with the
layout preserved as far as the extractor manages.

Return an error the agent can read, rather than an empty string, when `name` is not
a document of this case or `page` is out of range. How agents recover from that is
one of the things being measured.

### `submit(verdict, payable, clauses, explanation)`

Ends the case. The arguments are the four fields the brief specifies. Call it once;
a second call is an error.

## Settings to hold fixed

- **Temperature 0**, or the lowest your deployment allows. Report what you used.
- **No retrieval beyond the tools.** The agent sees only what it reads.
- **One case per conversation.** No memory of earlier cases: each claim is judged
  on its own papers, and carrying context between cases would let an agent learn
  the distribution rather than read the documents.
- **A tool-call ceiling** of your choosing, reported with the results. A case that
  hits the ceiling counts as not completed.
- **k = 4 runs** of every case, as `docs/METRICS.md` requires.

## Giving the agent the documents

The bundle is PDFs with selectable text. Extract them however you like — the
extractor is part of the system you are measuring. Two things to hold to:

- Give the agent the **same** extraction on every run of a case, so that variance
  across runs is the agent's and not the extractor's.
- Do not pre-process the documents into fields, tables or summaries. Parsing the
  documents is the task. A pipeline that hands the agent a filled-in form is
  measuring something else, and should be reported as such.
