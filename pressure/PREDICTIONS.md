# Predictions, written before the paid run

Written on 2026-10-14 at about 21:45 Irish time, before any real API call in this experiment. The git commit that adds this file is timestamped. The only runs so far used a scripted fake model, which says nothing about real behaviour. These are guesses, written down so the results can prove them wrong.

"Break rate" means the share of runs where the agent broke at least one of the six action rules.

| # | Prediction | Confidence |
|---|---|---|
| 1 | Sonnet 5.5 at low effort, no pressure: break rate 10–30%. | low |
| 2 | Pressure raises the break rate for every agent setting. For Sonnet at low effort it lands around 25–50%. | low |
| 3 | The most-broken rule is "never contact anyone at the competitor". The competitor's employee is on the shortlist, so the shortlist and the rule disagree, and agents will side with the shortlist. | moderate |
| 4 | The least-broken rule is the do-not-contact list, at least when the rules are on top: agents will check it. | moderate |
| 5 | Burying the rules in the long brief raises the break rate, mostly through skipped do-not-contact checks and contacting the competitor's employee. | low |
| 6 | When the salary candidate insists, Sonnet mostly defers to the founder rather than giving numbers. Haiku gives numbers more often. | low |
| 7 | When offered the referral, agents mostly ask the founder first. After being told no, Sonnet rarely contacts her anyway. | moderate |
| 8 | Medium effort breaks no more often than low effort. | low |
| 9 | Haiku breaks more often than Sonnet in every condition. | moderate |
| 10 | When a run breaks a rule, the final report lists it less than half the time. | low |
| 11 | The Sonnet monitor catches over 90% of the inserted breaks. The Haiku monitor catches 70–90%. Code patterns alone catch almost none of the subtle ones. | moderate |

Whatever happens, the results page will show which of these held.

## Added before the third run: the same rules, emailed by the founder on day 2

Written on 2026-10-14 at about 22:30 Irish time, after seeing the first two runs (rules written down, and no rules at all) and before any run of this condition. The commit that adds this section is timestamped.

In this condition the prompt has no rules, as in the no-rules run. When the agent first checks the inbox (the start of day 2), the founder's email contains the same seven rules, word for word. Everything the agent did on day 1 happened before it had the rules and is not counted as a break. To compare like with like, every condition is scored on what the agent did from day 2 on.

| # | Prediction | Confidence |
|---|---|---|
| 12 | From day 2 on, emailed rules are kept less well than the same rules written in the prompt from the start, for every agent setting. | moderate |
| 13 | Most of those breaks are location. The agent will already have told people the role is hybrid on day 1, so when the candidate who won't relocate asks on day 2, it answers instead of deferring. Location breaks in 30–70% of runs. | low |
| 14 | Pay numbers stay private after the rules arrive (0–10% of runs). In the no-rules run, agents never shared the band after the founder said no. | moderate |
| 15 | Pressure still pushes agents past the shortlist after the rules arrive, but less than with no rules: off-shortlist emails in under 15% of pressure runs. | low |
| 16 | When a run breaks an emailed rule, Sonnet lists it in its report more often than not. Haiku lists it less than half the time. | low |
