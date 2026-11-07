# Three-minute walkthrough script

Record this only after a real run works. Use synthetic details on screen, and do not
show your `.env` file. Speak your own results: replace each [BRACKET] with what
`raw_outputs/TEST_REPORT.md` says, including failures.

## 0:00–0:25 — The problem

"Most people with a consumer dispute can't get a lawyer straight away, and don't know
where to begin. I built NyaySaathi, an AI legal companion for Indian consumer
disputes. I kept the scope narrow on purpose, because in legal work, being reliable
in one area matters more than sounding confident in all of them."

*Show: the home page.*

## 0:25–1:05 — Understanding the problem

"I'll type a real-looking complaint: a defective phone and a refund that hasn't come."

*Paste: "I ordered a mobile phone online for Rs. 25,000. It was defective. I returned
it but have not received my refund even after 30 days."*

"It doesn't jump to a conclusion. It asks for the missing facts first. Once I answer,
it explains my options, and each legal point links to its source. The label shows how
well the answer is sourced. It's not my chance of winning."

*Show: follow-up questions, your answer, then the sources section. Briefly show a
Hindi or Hinglish message.*

## 1:05–1:45 — From story to action

"Build My Case organises my story and labels each fact as something I said, an AI
inference, or unverified, and I can correct anything. Know My Rights shows the
provision's official wording and link, with an action plan. Then I can generate a
refund request. It uses placeholders rather than making up details, and it's always
marked as a draft. The app never sends anything."

*Show: case labels, one rights card, the plan, the document and the DOCX download.*

## 1:45–2:25 — Stopping invented law

"The biggest risk is an AI inventing law. So I don't trust the model. The law comes
from provisions checked against official documents by a script. After the AI answers,
my code checks every citation. If it's unsupported, the AI gets one chance to fix it,
and otherwise the answer is blocked. Here I'm asking it to invent a section and a
Supreme Court judgment."

*Show: test 9's request in the chat, and the refusal.*

"Checking the real text also caught things a summary would miss: the 2021 limits, a
fee table replaced twice, and a 2026 amendment that only starts in January 2027."

## 2:25–3:00 — Honest results

"I ran [NUMBER] synthetic test cases, scored on ten criteria. [NUMBER] passed and
[NUMBER] failed. The most important failure was [YOUR MOST IMPORTANT FAILURE], and
[WHAT YOU DID OR WOULD DO ABOUT IT]. The checks prove citations exist, not that the
reasoning is right, and no lawyer has reviewed this yet, so that would be my next
step. Raw outputs and the report are in the repository. Thank you."
