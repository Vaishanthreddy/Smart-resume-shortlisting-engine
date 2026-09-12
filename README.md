# Smart Resume Shortlisting Engine

Upload one job description and any number of resumes. The application extracts what the
job actually asks for, searches every resume for explicit evidence, compares each
requirement against the resume by meaning, and produces a transparent relevance ranking
with the evidence behind every number.

It works on job descriptions and resumes it has never seen. Nothing is hard-coded for a
particular role, nothing is trained on the uploaded documents, and no language model
produces or influences a score.

---

## Contents

1. [What it does](#1-what-it-does)
2. [Architecture](#2-architecture)
3. [Why this is not a prompt-based scoring system](#3-why-this-is-not-a-prompt-based-scoring-system)
4. [Why supervised regression is not used](#4-why-supervised-regression-is-not-used)
5. [Keyword matching](#5-keyword-matching)
6. [Semantic matching](#6-semantic-matching)
7. [The seven score components](#7-the-seven-score-components)
8. [Weights and dynamic redistribution](#8-weights-and-dynamic-redistribution)
9. [Ranking and tie-breaking](#9-ranking-and-tie-breaking)
10. [Installation](#10-installation)
11. [Running the application](#11-running-the-application)
12. [Running the tests](#12-running-the-tests)
13. [API reference](#13-api-reference)
14. [Worked example: one candidate's final score](#14-worked-example-one-candidates-final-score)
15. [Privacy and fairness](#15-privacy-and-fairness)
16. [Known limitations](#16-known-limitations)
17. [Future work: learning to rank](#17-future-work-learning-to-rank)
18. [Judge demo script](#18-judge-demo-script)

---

## 1. What it does

Given an unseen job description and a set of unseen resumes in PDF, DOCX or TXT format,
the application:

- extracts requirements, required and preferred skills, responsibilities, education,
  certifications and soft skills from the JD with deterministic rules;
- parses each resume into sections, falling back to the whole document when a resume has
  no recognisable headings;
- performs explicit keyword matching against a canonical skill taxonomy with aliases;
- performs requirement-level semantic matching using sentence embeddings;
- computes seven component scores, each normalised to 0–100;
- combines them using weights that reflect what this particular JD asks for;
- ranks every candidate and explains the top three from stored evidence;
- shows matched requirements, the supporting snippet, and requirements for which no
  evidence was found.

No source-code change is needed for a new JD or a new set of resumes.

---

## 2. Architecture

```
Upload documents
    ↓  document_parser.py    PDF / DOCX / TXT, validation, partial-failure isolation
Extract and clean text
    ↓  text_cleaner.py       unicode folding, bullets, sentence splitting, chunking
Analyze JD requirements
    ↓  jd_analyzer.py        sections, indicator phrases, requirement statements
Parse resume sections
    ↓  section_parser.py     heading aliases, full-text fallback
Explicit skill and keyword matching
    ↓  keyword_matcher.py    alias index, word boundaries, conservative fuzzy pass
Requirement-level semantic matching
    ↓  semantic_matcher.py   cached model, batch encoding, cosine similarity
Project and experience relevance
    ↓  category_scorer.py
Education, certification and soft-skill checks
    ↓  category_scorer.py
Calculate transparent final score
    ↓  category_scorer.py    dynamic weights, penalties, clamping
Rank every candidate
    ↓  ranking_engine.py     deterministic multi-key sort
Generate top-three explanations
       explanation_generator.py
```

Layout:

```
smart-resume-shortlisting/
├── README.md
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py            FastAPI app, CORS, model warm-up
│   │   ├── config.py          every weight and threshold
│   │   ├── schemas.py         Pydantic models + converters
│   │   ├── api/routes.py      /api/health /api/analyze-jd /api/rank /api/compare
│   │   ├── services/          the ten pipeline modules listed above
│   │   └── data/skill_taxonomy.json
│   └── tests/                 pytest suite + synthetic fixtures
└── frontend/
    ├── package.json  vite.config.ts  tsconfig.json  tailwind.config.js
    ├── index.html  .env.example
    └── src/
        ├── main.tsx  App.tsx  index.css  types.ts
        ├── services/api.ts
        └── components/
            ├── FileUpload.tsx        JobAnalysis.tsx
            ├── RankingTable.tsx      CandidateDetails.tsx
            ├── CandidateComparison.tsx  TopCandidates.tsx
            ├── ScoreBreakdown.tsx    ErrorMessage.tsx
```

**Stack.** React + TypeScript + Vite + Tailwind CSS + Axios + Lucide React on the front
end. Python 3.11+, FastAPI, Uvicorn, Pydantic, PyMuPDF, python-docx,
sentence-transformers, scikit-learn, NumPy, RapidFuzz and pytest on the back end. The
default embedding model is `all-MiniLM-L6-v2`. No paid API and no API key is required.

---

## 3. Why this is not a prompt-based scoring system

The job description and the resume are never sent to a language model with a request for
a score, a rating or a ranking. A pretrained sentence-transformer is used for exactly one
operation: turning a string into a vector. Every number the recruiter sees is produced by
code in this repository that can be read, tested and stepped through.

This matters for three reasons:

- **Reproducibility.** The same inputs always produce the same output. `test_ranking_is_deterministic_across_runs`
  asserts it, including when the upload order changes.
- **Auditability.** Every component score decomposes into a countable quantity — skills
  matched out of skills required, requirements supported out of requirements stated — and
  every claim in an explanation is tied to a snippet lifted from the resume.
- **Defensibility.** A recruiter can be told precisely why candidate A ranked above
  candidate B, in points, per component, at the weights that were in force.

A generated score can be fluent and confidently wrong, cannot be decomposed, and changes
between runs. That is the wrong instrument for a decision that affects someone's
candidacy.

---

## 4. Why supervised regression is not used

A supervised model needs labelled ground truth: resumes scored by recruiters for a given
role. This project has none, and the evaluation documents are **testing inputs, not
training data**.

Training on them would be wrong in three separate ways. It would leak the evaluation set
into the model. It would need a train/test split carved out of roughly eighteen
documents, which is far too small for a stable estimate. And it would force invented
labels, so the model would learn the invention rather than relevance.

Instead the weights encode a stated, inspectable hypothesis about what relevance means.
They are visible in `config.py`, returned in every API response and displayed in the UI.
Disagreeing with them is easy, and changing them is a one-line edit rather than a
retraining run.

---

## 5. Keyword matching

`app/data/skill_taxonomy.json` holds around 240 canonical skills across programming
languages, frontend, backend, mobile, databases, cloud, DevOps, version control, testing,
data analysis, machine learning, generative AI, cybersecurity, networking, operating
systems, design tools, project management and business skills — plus soft skills with
behavioural cues, and certifications.

Each canonical skill owns its aliases:

```json
{
  "javascript": ["javascript", "java script", "js", "ecmascript"],
  "react": ["react", "react.js", "reactjs"],
  "node.js": ["node.js", "nodejs", "node js"],
  "rest api": ["rest api", "restful api", "rest services", "rest endpoints"],
  "aws": ["aws", "amazon web services"]
}
```

Implementation details that matter:

- **Boundaries.** Each alias compiles to `(?<![A-Za-z0-9+#])…(?![A-Za-z0-9+#])`, with
  punctuation tolerated between tokens, so `nodejs`, `node.js` and `node js` all match one
  canonical skill.
- **Short-token protection.** An alias of one or two characters — `C`, `R`, `Go` — only
  matches when it appears capitalised in the source document, and never inside a known
  ambiguous phrase such as `R&D`. `C` cannot match the `c` in "communication", and it
  cannot match inside `C++` because `+` is inside the boundary class.
- **Deduplication.** Results are keyed by canonical skill, so `Python`, `python` and
  `PYTHON` are one match.
- **Keyword stuffing resistance.** Scores are coverage ratios over a set. Repeating a
  skill forty times produces an identical match set, asserted by
  `test_keyword_stuffing_produces_the_same_match_set`.
- **Conservative fuzzy matching.** A RapidFuzz pass runs only on aliases of six characters
  or more, at a similarity cutoff of 92, and never overrides an exact match. It catches
  `kubernets`; it does not catch unrelated words.
- **Evidence.** Every match keeps the line it was found on, capped at two snippets.

---

## 6. Semantic matching

Whole-document similarity between a JD and a resume is a single blunt number: it rewards
length and shared vocabulary, and it cannot say which requirement was met. This engine
matches at the requirement level instead.

1. The JD is split into requirement statements, each tagged `required`, `preferred` or
   `responsibility`, with the section and confidence that produced the label.
2. Lines that are nothing but an enumeration of tools are flagged and excluded from the
   semantic set — those are already fully handled by the keyword components, and scoring
   them twice would double-count the same evidence.
3. Each resume is split into bounded chunks of 5–45 words.
4. Requirements and chunks are embedded in batches. The model loads once at start-up and
   is cached process-wide; embeddings are memoised, so the JD's requirement vectors are
   computed once and reused across all candidates.
5. For each requirement the best-matching chunk is found by cosine similarity, and the
   application stores the requirement text, the best evidence, the similarity, whether it
   passed the evidence threshold, and the requirement's type and importance.
6. Similarity is mapped to a 0–100 score through a floor and ceiling, then averaged with
   importance weights — `required` 1.0, `responsibility` 0.8, `preferred` 0.5 — so
   mandatory requirements count for more.

Whole-document similarity is still computed and returned as `whole_document_similarity`,
clearly labelled as a diagnostic. It carries no weight in the final score.

### Offline fallback

If the sentence-transformer cannot be loaded — no network, no cached model, package not
installed — the engine falls back to a deterministic lexical vector space built from
scikit-learn hashing vectorizers (word 1–2 grams plus character 4–5 grams), with its own
calibrated floor, ceiling and threshold. The application still runs end to end, the
active backend is reported by `/api/health`, in `model.backend` on every ranking response
and as a banner in the UI. Semantic quality is better with the transformer; install it to
get the intended behaviour.

---

## 7. The seven score components

Every component is normalised to 0–100 and clamped.

### Required skill coverage — 30%

Explicit mandatory skills only, taken from required and must-have JD statements. A
candidate matching two of three required skills scores `2 / 3 × 100 = 66.67`. Aliases
count; repetition does not.

### Semantic requirement matching — 25%

The importance-weighted average described above. Focused on responsibilities,
capabilities and contextual experience rather than on re-counting explicit skills.

Example of what it is for:

> JD requirement: "Develop and maintain RESTful backend services."
> Resume evidence: "Created Express endpoints for a web application."

No keyword is shared, but the meaning is.

### Other keyword coverage — 15%

Preferred skills, nice-to-have tools, domain terminology and role-specific non-mandatory
keywords. **Any skill already counted as required is removed from this set**, so nothing
is counted twice. `test_keywords_are_deduplicated_across_categories` asserts the two sets
never intersect.

### Project and experience relevance — 15%

Practical evidence from projects *or* employment — either alone is sufficient. A strong
academic project can carry an entry-level candidate, and relevant employment can carry an
experienced one. Computed as 70% requirement-relevance of project/experience passages plus
30% coverage of the JD's key skills *demonstrated inside* that practical text rather than
only listed in a skills block. Project count and years alone earn nothing.

### Education match — 5%

Only education the JD explicitly requested. Degree level contributes 60% and field of
study 40%; a degree one level below the requested level earns partial credit. Unrelated
degrees earn nothing, and when the JD states no education requirement the component is
switched off rather than scored as zero.

### Certification match — 5%

Only certifications the JD requested, matched canonically or by approximate wording.
Unrelated certifications earn nothing. Absent from the JD means the component is inactive.

### Soft-skill evidence — 5%

A soft skill scores only when it appears in the JD **and** the resume contains supporting
evidence. Listing "teamwork" in a skills block earns nothing; "Collaborated with a
four-member development team" does. Behavioural cue phrases earn full credit, contextual
similarity earns partial credit. The weight is deliberately low and the explanations are
deliberately cautious.

### Avoiding double-counting

The four large components are deliberately disjoint: required skills are explicit
mandatory terms; other keywords are the same kind of evidence with required terms
subtracted; semantic matching runs on requirement *statements* with pure skill lists
removed; project relevance runs the same statements against a restricted section of the
resume to ask a different question — not "is it mentioned" but "was it done".

---

## 8. Weights and dynamic redistribution

```
CORE MATCHING
Required skill coverage             30%
Semantic requirement matching       25%
Other keyword coverage              15%
                                  -----
Core matching total                 70%

SUPPORTING EVIDENCE
Project and experience relevance    15%
Education match                      5%
Certification match                  5%
Soft-skill evidence                  5%
                                  -----
Supporting evidence total           30%

TOTAL                              100%
```

```
final_score =
    0.30 × required_skill_score
  + 0.25 × semantic_score
  + 0.15 × other_keyword_score
  + 0.15 × project_experience_score
  + 0.05 × education_score
  + 0.05 × certification_score
  + 0.05 × soft_skill_score
```

Not every JD contains all seven categories, and a candidate must not lose points because
a category is absent. For each JD the engine detects which components are applicable,
marks the rest inactive, and redistributes the inactive weight **proportionally** among
the active components so their relative importance is preserved and the active weights
total exactly 1.0.

If a JD mentions no certification, the 5% certification weight is shared out and required
skills become `0.30 / 0.95 = 31.58%`. The effective weights are returned in
`scoring.effective_weights`, displayed in the left-hand panel of the UI alongside the base
weight, and applied identically to every candidate for that JD. Weights are never
redistributed per candidate.

### Mandatory-skill penalty

Optional, configurable and always disclosed. It applies only to skills the JD marked
mandatory with an explicit indicator phrase, deducts 2 points each up to a cap of 10, uses
the same rule for every candidate, and is shown as its own line in the score breakdown.
Set `MANDATORY_SKILL_PENALTY_ENABLED=false` to turn it off.

---

## 9. Ranking and tie-breaking

Candidates are sorted by, in order:

1. higher final score,
2. higher required-skill score,
3. higher semantic score,
4. higher project/experience score,
5. candidate identifier, alphabetically.

Identifiers are assigned from the alphabetically sorted filenames, so the ranking does not
depend on upload order. The application returns a **relevance ranking only** — never a
hire or reject decision.

---

## 10. Installation

Requires Python 3.11+ and Node.js 18+.

### Backend

**Unix / macOS**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Windows PowerShell**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

The first run downloads `all-MiniLM-L6-v2` (about 90 MB) from Hugging Face and caches it.
To pre-download it:

```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

If the machine is offline, set `FORCE_FALLBACK_EMBEDDINGS=true` in `.env` and the lexical
fallback is used instead.

### Frontend

**Unix / macOS**

```bash
cd frontend
npm install
cp .env.example .env
```

**Windows PowerShell**

```powershell
cd frontend
npm install
Copy-Item .env.example .env
```

---

## 11. Running the application

Two terminals.

**Backend**

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: <http://localhost:8000/docs>

**Frontend**

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>.

The backend URL comes from `VITE_API_BASE_URL` and is never hard-coded. To point at a
different host, edit `frontend/.env`. CORS origins are configured through `CORS_ORIGINS`
in `backend/.env`.

---

## 12. Running the tests

```bash
cd backend
pytest
```

92 tests covering PDF/DOCX/TXT parsing, empty-file rejection, skill aliases,
required/preferred classification, short-token false-positive prevention, keyword
deduplication, keyword-stuffing resistance, semantic score range, requirement-level
evidence selection, every component calculation, the base formula, dynamic weight
redistribution, 0–100 bounds, deterministic tie-breaking, transparent penalties, partial
failure for malformed resumes, and broad ordering of synthetic strong, medium and weak
resumes.

All fixtures are synthetic and defined in `tests/conftest.py`. No hackathon evaluation
document is used anywhere in the suite. The tests set `FORCE_FALLBACK_EMBEDDINGS=true` so
they run offline in a few seconds.

---

## 13. API reference

### `GET /api/health`

```json
{
  "status": "ok",
  "version": "1.0.0",
  "semantic_model_status": "ready",
  "model_name": "all-MiniLM-L6-v2",
  "model_backend": "sentence-transformers",
  "taxonomy_version": "1.0.0",
  "detail": "Sentence-transformer loaded."
}
```

### `POST /api/analyze-jd`

Multipart with `jd_file`. Returns the structured JD analysis, the active components, the
effective weights and any bias flags.

### `POST /api/rank`

Multipart with `jd_file` and repeated `resume_files`. Returns:

```json
{
  "result_id": "…",
  "job": {
    "title": "string",
    "required_skills": [], "preferred_skills": [], "other_keywords": [],
    "responsibilities": [], "education_requirements": [],
    "certification_requirements": [], "soft_skills": [], "bias_flags": []
  },
  "scoring": {
    "base_weights": {}, "effective_weights": {},
    "active_components": [], "inactive_components": []
  },
  "summary": { "total_candidates": 18, "successfully_processed": 18, "failed_files": [] },
  "candidates": [
    {
      "rank": 1,
      "candidate_id": "candidate-01",
      "candidate_name": "string",
      "filename": "string",
      "final_score": 87.4,
      "component_scores": {
        "required_skills": 90.0, "semantic_match": 86.0, "other_keywords": 75.0,
        "project_experience": 88.0, "education": 100.0, "certifications": 0.0,
        "soft_skills": 70.0
      },
      "weighted_contributions": {},
      "matched_required_skills": [], "matched_other_keywords": [],
      "required_skills_not_found": [], "semantic_evidence": [],
      "project_experience_evidence": [], "education_evidence": [],
      "certification_evidence": [], "soft_skill_evidence": [],
      "penalties": [], "explanation": "string"
    }
  ],
  "model": { "name": "all-MiniLM-L6-v2", "backend": "sentence-transformers", "note": "" }
}
```

A resume that cannot be parsed appears in `summary.failed_files` with a message that says
what to do about it; the remaining candidates are still ranked.

### `POST /api/compare`

JSON body `{ "result_id": "…", "candidate_a_id": "candidate-01", "candidate_b_id": "candidate-04" }`.
Returns component-score differences at the effective weights, matched-skill differences,
evidence differences, requirements not found for each, and a deterministic explanation of
the ranking order. The `result_id` comes from the ranking response; results are held in a
bounded in-memory cache of derived scores only.

---

## 14. Worked example: one candidate's final score

From the live run in `backend/tests` style fixtures — a Junior Data Analyst JD asking for
Python, SQL, Power BI, data visualization, statistics and Excel, with preferred AWS,
Tableau and Looker, a Bachelor's in Computer Science or Statistics, a Power BI
certification, and communication plus teamwork.

All seven components are active, so the effective weights equal the base weights.

| Component | Score | How it was obtained | Weight | Points |
|---|---:|---|---:|---:|
| Required skill coverage | 100.0 | 6 of 6 required skills matched | 30% | 30.00 |
| Semantic requirement matching | 59.1 | importance-weighted average over 11 requirement statements, 8 supported by evidence | 25% | 14.77 |
| Other keyword coverage | 60.0 | 3 of 5 (`aws`, `etl`, `sales`); `tableau` and `looker` not found | 15% | 9.00 |
| Project and experience relevance | 69.4 | 0.70 × responsibility relevance + 0.30 × skills demonstrated in experience text | 15% | 10.41 |
| Education match | 100.0 | Bachelor of Science in Statistics meets level and field | 5% | 5.00 |
| Certification match | 100.0 | "Microsoft Power BI Data Analyst (PL-300)" matched | 5% | 5.00 |
| Soft-skill evidence | 100.0 | "Collaborated with a four-member marketing team…" and "Presented monthly… findings…" | 5% | 5.00 |
| **Final score** | | no mandatory skill missing, so no penalty | | **79.17** |

The strongest semantic pair driving that 59.1:

> requirement "Collaborate with the marketing team to define reporting requirements."
> evidence "Collaborated with a four-member marketing team to define reporting requirements." — similarity 0.81

Every one of those numbers is visible in the candidate detail drawer, and the stacked bar
beside each candidate in the ranking table draws the Points column directly.

---

## 15. Privacy and fairness

- **Nothing is stored.** Uploaded files are parsed in memory and discarded. No document is
  written to disk unless `PERSIST_UPLOADS=true` is set deliberately. The comparison cache
  holds derived scores and evidence snippets, never files, and is bounded.
- **Protected characteristics are never inferred or used.** Name, gender, age, photograph,
  address, religion, nationality and marital status play no part in any component. The
  candidate name is extracted for display only and is never passed to a scoring function.
- **Formatting is not penalised.** A resume with no headings falls back to full-document
  parsing and can still score 100 on required skills; `test_missing_headings_do_not_penalise_a_candidate`
  asserts it.
- **Evidence is never fabricated.** Every snippet in an explanation is a substring of the
  submitted resume. Absence is always phrased as "No evidence of X was found in the
  submitted resume", never as a claim about the person.
- **No decisions.** The API returns relevance ranking only. There is no hire/reject label
  anywhere in the system.
- **Bias review is advisory.** The JD bias analyzer reads only the job description, flags
  gender-coded and age-coded wording, "native speaker" phrasing, unrealistic experience
  demands and excessive requirement lists, and never touches a score.
  `test_flags_never_change_the_scoring_plan` asserts it.
- **Logs are safe.** Character counts and page counts are logged; resume content is not.

This is a decision-support tool. A human should read the shortlisted resumes.

---

## 16. Known limitations

- **Taxonomy coverage.** A skill absent from `skill_taxonomy.json` is invisible to the
  keyword components. The semantic component partially compensates, but adding an entry is
  the real fix — it is plain JSON.
- **Weights are a hypothesis, not a finding.** They encode a reasonable view of relevance;
  they are not derived from recruiter behaviour.
- **Section detection is heuristic.** Multi-column PDF layouts can interleave text and
  blur section boundaries. The full-text fallback keeps such resumes scoreable.
- **Image-only PDFs are rejected**, not OCR'd. The error names the file and says what to
  upload instead.
- **Seniority is only lightly modelled.** Years of experience are extracted and reported,
  but relevance is scored from evidence rather than from tenure.
- **Soft-skill inference is shallow** by design. Cue phrases and sentence similarity are
  weak proxies for a behavioural competency, which is why the weight is 5%.
- **The lexical fallback is weaker** than the transformer at matching paraphrases that
  share no vocabulary. It exists to keep the application usable offline.
- **Single-language.** Tested against English documents only.

---

## 17. Future work: learning to rank

If recruiter-labelled data became available — shortlist decisions, interview outcomes, or
pairwise "A is a better fit than B" judgements — the natural next step is learning to rank
rather than regression onto an invented score.

The current component scores are already a clean feature vector: seven normalised values
plus coverage counts, evidence counts and similarity statistics. A pairwise ranker such as
LambdaMART or a linear RankSVM could learn weights from preference pairs, which are far
easier for recruiters to produce honestly than absolute scores, and which sidestep
calibration across different roles.

Three conditions would need to hold. Labels grouped by job, so learning happens within a
role rather than across unrelated ones. Enough labelled pairs to beat the hand-set weights
under cross-validation by role, not by document. And a fairness audit of the learned
weights, since a model trained on historical shortlists will faithfully reproduce whatever
bias those shortlists contained — the current weights at least have the virtue of being
visible. Until then, the transparent formula is the more defensible instrument, and it
would remain the fallback whenever a role has too little labelled data.

---

## 18. Judge demo script

About five minutes.

1. **Show that nothing is pre-loaded.** Open <http://localhost:5173>. The upload screen and
   the four pipeline steps are all that exist. Point at the header chip showing which
   embedding backend is live.

2. **Upload and rank.** Drop the JD into the left zone and all resumes into the right.
   Note the button stays disabled until both are present. Press **Rank candidates**.

3. **Read the left panel first.** This is the JD the engine inferred: title, required
   skills, preferred keywords, responsibilities, education, certifications, soft skills.
   None of it was hard-coded. Scroll to the weights and show any inactive component —
   *"this JD never mentions certifications, so that 5% is redistributed proportionally,
   and no candidate is punished for it."*

4. **Top three.** Each stacked bar is the final score drawn as its weighted parts, so the
   source of the score is visible at a glance. Read one explanation aloud and point out
   that each claim carries a quoted snippet from that resume.

5. **Open a detail drawer.** Show the score arithmetic table — component, score, effective
   weight, points, penalty, total. Scroll to requirement-to-evidence pairs and find a pair
   that shares no keywords, for example *"Develop and maintain RESTful backend services"*
   matched to *"Created Express endpoints for a web application"*. This is the semantic
   component doing work keyword matching cannot.

6. **Show the gaps.** Scroll to requirements not found and read the wording: *"No evidence
   of AWS was found in the submitted resume."* Not a claim about the candidate.

7. **Compare two candidates.** Pick rank 1 and rank 3. The explanation gives the gap in
   points and attributes it to specific components at their effective weights.

8. **Show robustness.** Add a scanned or corrupt PDF and re-rank: it appears in the failed
   files banner with a specific message while everyone else is still ranked.

9. **Close in the terminal.** `pytest` — 92 passing, including keyword-stuffing resistance,
   short-token protection, weight redistribution and deterministic tie-breaking. Then
   `grep -ri "score" backend/app/services/semantic_matcher.py` to show the model is only
   ever asked to `encode`.
