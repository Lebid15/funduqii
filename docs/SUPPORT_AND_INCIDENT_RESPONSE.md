# Funduqii — Support & Incident Response

> **Status:** process established in **Phase 1.7**. Documentation only — no
> ticketing/incident tooling is built now. This defines how issues are triaged
> and how incidents are handled.

---

## 1. Report types

- **Bug** — something works incorrectly.
- **Outage** — a service is down or unusable.
- **Performance** — slowness / degradation.
- **Security** — suspected breach, abuse, or vulnerability.
- **Data** — suspected data loss/corruption or isolation concern.
- **Request** — how-to / configuration / feature question.

## 2. Severity levels

| Level | Meaning | Example |
|---|---|---|
| **low** | Minor, workaround exists | cosmetic UI issue, single how-to question |
| **medium** | Impacts some users, no data risk | a booking form error for one hotel |
| **high** | Broad impact or blocked core flow | login failures, payment error, general slowness |
| **critical** | Outage / data / security | server down, WhatsApp pipeline down, data/isolation breach |

Examples map directly: **login failure** → high; **booking error** → medium/high;
**payment error** → high; **general slowness** → high; **WhatsApp down** →
high/critical (non-critical messaging degrades, not core ops); **server down** →
critical.

## 3. Handling a critical incident

1. **Acknowledge & declare** the incident; assign an owner.
2. **Assess impact** — who/what is affected; is data or security at risk?
3. **Mitigate** — restore service (rollback, restart, failover, maintenance
   mode); stop the bleeding before root-causing.
4. **Communicate** — status to stakeholders during the incident.
5. **Resolve** — confirm health checks pass; verify data integrity.
6. **Post-mortem** — root cause, timeline, and follow-up actions (blameless).

## 4. Dependencies

- **Detection** relies on monitoring/alerts
  ([MONITORING_AND_OBSERVABILITY_STRATEGY.md](MONITORING_AND_OBSERVABILITY_STRATEGY.md)).
- **Data incidents** use backup/restore runbooks
  ([BACKUP_AND_RESTORE_STRATEGY.md](BACKUP_AND_RESTORE_STRATEGY.md)).
- **Security incidents** use the security checklist and (later) audit log
  ([SECURITY_AND_FIREWALL_CHECKLIST.md](SECURITY_AND_FIREWALL_CHECKLIST.md),
  [AUDIT_LOG_STRATEGY.md](AUDIT_LOG_STRATEGY.md)).

## 5. Incident log (later)

An **incident log** (date, severity, impact, timeline, resolution, follow-ups)
is required once operations begin — for accountability and to prevent repeats.

## Out of scope for Phase 1.7

No ticketing system, on-call rotation, or incident tooling is built now. This is
the process to follow when support operations begin.
