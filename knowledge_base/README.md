# Legal knowledge base

The only legal information NyaySaathi may cite comes from this folder. If a
provision is not here, the assistant must say it could not verify it.

**Status:** 9 official documents and 37 provisions, last reviewed on 6 November
2026. Run `python scripts/verify_sources.py` to check every quote against the
official documents. **No qualified lawyer has reviewed this knowledge base.**

## Points that are easy to get wrong

- **Value limits:** section 34 of the Act still says one crore, but the 2021
  Jurisdiction Rules set the District Commission's limit at fifty lakh rupees.
  The helpline's knowledge base still showed the older figures when last checked.
- **Filing fees:** the 2020 fee table was replaced in 2022 and again in 2023. Use
  the 2023 table.
- **E-Commerce Rules 2026 amendment:** published on 9 September 2026, but in force
  only from 1 January 2027. `in_force_from` and `superseded_from` handle the switch
  automatically. Only rule 4(5) of the amendment is in the knowledge base so far.

## Known gaps

- Whether an advocate is needed to file on e-Jagriti. The official workflow lists a
  Vakalatnama, but the e-Jagriti FAQ page could not be read by our tools.
- Reserve Bank of India refund timelines, bank disputes and the RBI Ombudsman.
- The National Commission's value limit is in the rules, but has no entry yet.
- India Code's copy of the Act was read as published. A later amendment to the Act
  would not be caught automatically.

## Rules for adding a source

1. Prefer official primary sources: India Code, the Department of Consumer
   Affairs, the National Consumer Helpline, e-Jagriti and the NCDRC.
2. Do not add a provision unless its text was read from the source at the
   recorded URL.
3. Record the date of verification. Do not assume older procedures, fees,
   limits or deadlines still apply.
4. Do not add case law to the first version.

## What each entry in `sources.json` records

| Field | Meaning |
| --- | --- |
| `id` | Short unique ID that the model cites and the validator checks |
| `title` | Official name of the document |
| `url` | Official link |
| `provision` | Section or rule number, if one exists |
| `text` | Wording taken from the source |
| `plain_language` | Simple explanation, written by us and marked as such |
| `domain` | Legal domain, such as `consumer`, so other domains can be added later |
| `last_verified` | Date someone last checked it against the source |
