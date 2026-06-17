# Glossary — Hebrew ↔ system terms

The branch and its docs speak **Hebrew**; the system's data/identifiers are
**English** (enum values, table/field names). This table pins the mapping so the
agent maps a user's Hebrew term to the exact system identifier (and back) without
guessing. Use the **System ID** verbatim when querying/validating; use the Hebrew
when speaking to users.

## Populations
| Hebrew | System ID | Notes |
|--------|-----------|-------|
| קבע | `KEVA` | career personnel — annual quota (2 week / 4 day) |
| סדיר | `SADIR` | mandatory service — balanced by burden, no cap |

## Classifications (network ports & computers)
| Hebrew | System ID |
|--------|-----------|
| אזרחי | `CIVILIAN` |
| גלובל | `GLOBAL` |
| סודי | `SECRET` |
| סודי ביותר | `TOP_SECRET` |

> ⚠️ **To confirm:** the infosec doc (`04-infosec`) references **`שמור`** ("restricted") as a level — "בסיווג מעל שמור (שמור, סודי, סודי ביותר)". The system enum has no `שמור`. Decide whether `שמור` is a real 5th level to add, or maps to an existing one.

## Ranks
| Hebrew | System ID |
|--------|-----------|
| סגן | `LIEUTENANT` |
| סרן | `CAPTAIN` |
| רב-סרן | `MAJOR` |

(רע"ן / סגן-אלוף = branch head, above the modeled ranks.)

## Duty types (shifts & missions)
| Hebrew | System ID | Notes |
|--------|-----------|-------|
| שמירה שבועית | `WEEK_LONG` | week-long guard shift (7 pts) |
| שמירה יומית / לילית | `SINGLE_DAY` | single day or night (1 pt; day = night) |
| תורנות מענה / כוננות תמיכה | `SUPPORT` | 24/7 customer-ticket standby; Sadir-only *(confirm the official Hebrew term)* |
| משימה מתפרצת | `AdHocMission` | sudden mission (ceremony, memorial, volunteering) |

## Roles (permissions)
| Hebrew | System ID |
|--------|-----------|
| אחראי רשת | `NETWORK_MANAGER` |
| אחראי לוגיסטיקה | `LOGISTICS_OFFICER` |
| אחראי תורנויות (קבע/סדיר) + אחראי משימות מתפרצות | `SHIFT_MANAGER` |

> ⚠️ **To confirm:** the branch role list (`06-roles-and-responsibilities`) is richer than the 3 system roles — separate `אחראי תורנויות קבע`, `אחראי תורנויות סדיר`, `אחראי משימות מתפרצות`, plus `אחראי בטחון מידע`, `אחראי חינוך`, etc. Decide whether to split/add system roles or keep the 3 broad ones.

## Network
| Hebrew | System term |
|--------|-------------|
| סוויץ' | Switch |
| פורט | Port (`CONNECTED` = מחובר, `DISCONNECTED` = מנותק) |
| נקודת קיר | WallJack |

## Equipment (logistics)
| Hebrew | System term |
|--------|-------------|
| מחשב | Computer |
| מסך | Monitor |
| מספר קטלוגי | catalog_number |
| תקין | `FUNCTIONAL` |
| תקול | `BROKEN` |
| בפירמוט | `FORMATTING` |
| מוכן לאיסוף | `READY_FOR_PICKUP` |
| במלאי / זמין | `READY_TO_USE` |
| בשימוש | `IN_USE` |
| הוצא משירות (לא ניתן לתיקון) | `DECOMMISSIONED` |
| מחסן / מלאי (מספר אישי 1234567) | the depot / default holder |

## Concepts
| Hebrew | System term |
|--------|-------------|
| טבלת הצדק | Justice Table (fairness balancing) |
| פנייה (רשת / ציוד) | Ticket (`NETWORK_REQUEST` / `EQUIPMENT_REQUEST`) |
| פנקס מטווחים / בוחן בטיחות בנשק | range qualification (`last_range_qualification`, HC-GD-9) |
| מדור | OrgUnit (`DEPARTMENT`) |
| צוות | OrgUnit (`TEAM`) |
| ראש צוות | team leader (`OrgUnit.leader_id`) |
| ראש לשכה ענפי | branch office head (handles user-opening forms, Elbit cards) |
| משרת / חייל | Personnel |
| מספר אישי | personal_number (login) |
