# Knowledge base

Reference content served and explained by the **General Knowledge Agent** (§7.5 in
DESIGN.md). Static markdown — easy to edit, version in git. The agent retrieves the
relevant doc, explains it (in Hebrew or English), and serves any linked files/URLs.

Policy/procedure text is kept **verbatim (Hebrew)** so the official wording isn't
distorted in paraphrase.

| Doc | Covers | Source |
|-----|--------|--------|
| `00-glossary.md` | Hebrew ↔ system-identifier mapping (so the agent stays consistent) | bridge |
| `01-branch-intro.md` | Branch 300 (CombatAI): general + structure (מדורים/צוותים) | branch content |
| `02-open-closed-networks.md` | Opening a user to the classified networks (user form + network process) | נהלים §3.3 |
| `03-shift-readiness.md` | Pre-shift readiness: range booklet + weapon-safety test (half-yearly) | נהלים §3.2 |
| `04-infosec.md` | Information-security rules (נהלי בטחון מידע) | נהלים §1 |
| `05-fairness-explained.md` | Balancing & fairness mechanics, plain language | derived from design |
| `06-roles-and-responsibilities.md` | Branch role-holders + staff list | בעלי תפקידים |
| `07-site-and-general-procedures.md` | Elbit site security + general procedures | נהלים §2 + §3 |
| `08-whatsapp-groups.md` | Branch 300 WhatsApp groups — main, building (אנשי אילן), and per-section | branch content |

**Data-backed (not docs):** the live "branch structure" query (teams, **leaders +
contacts**) and a person's **own details** read from the database (`OrgUnit`,
`Personnel`).

**Still placeholder:** in `03`, the **SmartBase URL** and the **weapon-safety file**
are placeholders — swap in the real ones. Everything else is real branch content.

Per the no-fabrication rule: if a topic has no content here, the agent says it
doesn't have the information rather than inventing it.
