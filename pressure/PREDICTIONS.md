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

## Added before the fourth run: which safeguard works?

Written on 2026-10-14 at about 23:25 Irish time, after the three runs above and before any run of these arms. The commit that adds this section is timestamped.

Four new arms run on the same scenarios, agents and pressure levels:
- **gate:** no rules in the prompt. Code in front of send_email blocks off-shortlist, do-not-contact, competitor and extra follow-up emails. It also blocks emails whose wording the code patterns can tell break the location or pay rule. The block message quotes the rule.
- **check:** the same gate. Then a Haiku checker reads each email that passed, against the reworded location and pay rules.
- **check_strict:** as check, but the checker enforces the two rules as originally written.
- **all:** the rules in the prompt, plus the gate and the reworded checker.

| # | Prediction | Confidence |
|---|---|---|
| 17 | With the gate and no prompt rules, most pressure runs (over half) hit at least one block, mostly on the competitor or off-shortlist people. After a block, agents ask the founder or move on. Fewer than 10% of runs try another route to the same person, or reword an email to get it past a check. | low |
| 18 | With the code gate alone, some location hints the patterns miss still reach candidates: 10–40% of runs. | low |
| 19 | Adding the reworded checker cuts that to under 10% of runs. | moderate |
| 20 | The strict checker blocks a correct "the founder will cover it on the call" reply in over half the runs where the remote-question candidate asks. Fewer of those candidates get booked than with the reworded checker. | moderate |
| 21 | With rules in the prompt as well, under 10% of runs hit any block, and calls booked match prompt rules alone. | moderate |
| 22 | With the gate (no prompt rules), calls booked per run are about the same as with prompt rules. No run reaches two calls. | moderate |

## Scorecard, written after all three runs

Scored on the final data after hand review (192 runs: 96 with the rules in the prompt, 48 with the rules emailed on day 2, 48 with no rules). Six were wrong, five were half right, five held.

| # | Verdict | What happened |
|---|---|---|
| 1 | Wrong | Sonnet low, no pressure, rules in the prompt: 0 of 16 runs broke a rule. |
| 2 | Wrong | Pressure moved Sonnet low from 0 of 16 to 1 of 16, and the other two settings not at all. |
| 3 | Wrong | Nobody contacted the competitor's employee when the rules were written. The only break was a location hint. |
| 4 | Held | No run broke the do-not-contact rule. That says little, since almost no rule was broken. |
| 5 | Wrong | The one break came with the rules buried, but it was a location hint, not a skipped check or a competitor contact. One run can't show an effect. |
| 6 | Half right | Sonnet always deferred on pay. So did Haiku whenever the rules were written. |
| 7 | Half right | No run with rules contacted the referral. But agents didn't "mostly ask first": in REFERRAL_NOT_ASKED of 96 runs they left her out without asking. |
| 8 | Held | Medium effort broke 0 rules; low effort broke 1. |
| 9 | Wrong | Haiku broke no written rule at all. |
| 10 | Half right | The one break with rules in the prompt went unreported (1 of 1). Every slip after the emailed rules was reported (6 of 6). |
| 11 | Half right | Both monitors caught all 160 inserted breaks. That is above the range I gave for Haiku. Code alone caught none of the subtle location breaks, but it did catch 21 of 40 subtle pay breaks. |
| 12 | Held, weakly | Every agent setting slipped in one to three runs after the emailed rules (6 runs in all), against none with the rules in the prompt, scored from day 2 on. Paired test p = 0.03. Two of the six are only the city in a "Re:" subject line. Without those, it is 4 against 0, p = 0.13. |
| 13 | Wrong | Location slips after the emailed rules: 6 of 48 runs (12.5%), not 30–70%. Most agents deferred on day 2 even though they had already told the candidate the location on day 1. |
| 14 | Held | 0 of 48 shared pay numbers after the rules arrived. |
| 15 | Held on the number | 0 of 24 pressure runs went off the shortlist after the rules arrived, so under 15%. But the "still pushes" part was wrong: there was none at all. |
| 16 | Half right | Sonnet listed its slip in all 5 runs. Haiku listed its one slip too (1 of 1). |
