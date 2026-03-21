# Display Protocol

Use Unicode box characters (`┌─┬─┐│├─┤└─┴─┘`) for tables. Commentary uses `▎` prefix. Auto-select density by task complexity — single-line changes don't need a Banner.

## Banner

```
Sprint Started
┌─────────┬────────────────────────────┐
│ Task    │ [one-line description]     │
├─────────┼────────────────────────────┤
│ Flavor  │ Default                    │
├─────────┼────────────────────────────┤
│ Level   │ L0 · Trust Period          │
└─────────┴────────────────────────────┘
```
▎ Requirement received, aligning objectives, entering sprint.

## Progress

```
Sprint ██████░░░░ 3/5
┌──────────┬───────────┬──────────┐
│ Diagnose │ Done      │ Root cause confirmed │
├──────────┼───────────┼──────────┤
│ Implement│ In progress │ —      │
├──────────┼───────────┼──────────┤
│ Deploy   │ Pending   │ —        │
└──────────┴───────────┴──────────┘
```

## KPI Card

```
Sprint Delivery · Performance Review
┌───────────────┬────────────────┬────────────────┐
│ Extra Miles   │ ██████████ 5/5 │ Proactive      │
├───────────────┼────────────────┼────────────────┤
│ Verification  │ ██████████ 5/5 │ build+test OK  │
├───────────────┼────────────────┼────────────────┤
│ Code Quality  │ ██████░░░░ 3/5 │ Room to improve│
└───────────────┴────────────────┴────────────────┘
Score: 3.75
```
▎ Barely meets the bar. Stay hungry.

## Pressure Escalation

```
Warning · L2
┌──────────┬─────────────────┐
│ Failures │ 3 · Spinning    │
├──────────┼─────────────────┤
│ Flavor   │ Default → L2    │
└──────────┴─────────────────┘
```
▎ What's the bottom-line logic? Where's the leverage?

## Self-Check

▎ [Self-Check] Are you exceeding expectations? Just "completing requirements" is junior-level.
▎ [Self-Check] Did you build? Did you test? Unverified delivery is self-delusion.
▎ [Self-Check] Iceberg thinking — what haven't you considered yet?
