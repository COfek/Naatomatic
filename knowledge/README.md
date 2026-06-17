# Knowledge base

Reference content served and explained by the **General Knowledge Agent** (§ in
DESIGN.md). These are static markdown docs — easy to edit and version. The agent
retrieves the relevant doc, explains it in plain language, and serves any linked
files/URLs.

| Doc | Covers |
|-----|--------|
| `01-branch-intro.md` | What the CombatAI branch is (intro) |
| `02-open-closed-networks.md` | How to open a user to the closed networks |
| `03-shift-readiness.md` | Pre-shift "debts": range qualification + weapon-safety test |
| `04-infosec.md` | Information security — what NOT to do in the office |
| `05-fairness-explained.md` | Balancing & fairness mechanics, in plain language |

Branch **structure** (departments/teams/leaders) and a person's **own details**
are data-backed (read live from the DB), not static docs.

> **Status: the content here is placeholder/draft** (except `05-fairness-explained`,
> which is derived from the system design). The agent answers *from* these docs, so
> replace them with the branch's real material — intro, procedures, the actual
> SmartBase URL + weapon-safety file, and the real infosec policy. If a topic has no
> real content, the agent says it doesn't have the information rather than inventing it.
