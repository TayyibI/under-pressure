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
