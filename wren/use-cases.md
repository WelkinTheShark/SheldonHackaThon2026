# Wren use-case tests

Run these in Seldon (Wren) against the deployed URL. `seldon.yml` at the repo root holds the same
tests in Seldon's format; keep the two in step. W1 and W2 are the two required core workflows.
Runs cost $3 each after the first 10.

**Keep them fast.** Each test is short and checks one thing. Every test starts with the same
instruction: keep Simulated responses on (if the red "Demo only: Simulate responses" banner is not
at the top, click Simulate responses once and never click Turn off), use only the controls the steps
name, do not open other pages, menus, the leaderboard or User management unless a step says to, and
finish as soon as the last result is visible. Without it, Wren explores the whole page and a test
takes 15 minutes or more.

**Simulated responses.** Test runs use canned replies and no Anthropic spend; rows are marked
Simulated. Expected results check labels and amounts, never Claude's wording.

**Budgets.** Every user's budget defaults to $1000, and so does the shared team budget.

**Sign-in.** Every test signs in as `wren`, an All-access demo login (`python -m app.devs add "wren"
--team Demo --access all`, then `python -m app.devs password "wren"`). Without it, Wren makes its
own Self-access login, which can't move the Routing level slider. Use a demo-only password.

**No reset.** Live calls already holds older rows. New rows appear at the top, and each test
checks only the rows it adds.

**One shared app.** Budget, Use recommended model and Routing level are global, and Seldon runs a
suite's cases at the same time, so W1, W2, W5 and W7 must each run on their own (`only: true` in
`seldon.yml`). The others can run together.

## W1: Catch and fix overkill (required)

1. Set Routing level to Balanced and make sure Use recommended model is off.
2. Enter "Write a commit message for: fix typo in README" and click Run this prompt.
3. Turn Use recommended model on and click Run this prompt again.

Expected: of the two new rows, the older is on Opus 5.5 with status Overkill and the newer is on
Haiku 5.5 with status Downshifted.

## W2: Enforce a budget (required)

1. Read the spent amount in "$X spent of $Y budget" at the top right.
2. Click Edit budget, enter that spent amount, and click Save.
3. Enter "Write a commit message for: fix typo in README" and click Run this prompt.
4. Click Edit budget, enter 1000, click Save, and click Run this prompt again.

Expected: the first new row is Blocked by budget and the spent amount did not change after it; the
second new row is not Blocked by budget.

## W4: Roast a prompt

1. Enter "You are an expert. Please summarize this. Please summarize this."
2. Click Roast this prompt.

Expected: the Roast window shows a recommended model with a reason, at least one issue and a
suggested fix, and no score.

## W4b: Take or override the recommended model

1. Enter "Write a commit message for: fix typo in README".
2. Click Roast this prompt, then close the Roast window.
3. Click Run on recommended model.
4. Pick Opus 5.5 in the menu beside Run this prompt and click Run this prompt.

Expected: after the roast the Roast button reads Run on recommended model; of the two new rows, the
older is on Haiku 5.5 with status OK and the newer is on Opus 5.5 with status Overkill.

## W4c: Roast a call that already ran

1. Enter "Write a commit message for: fix typo in README" and click Run this prompt.
2. Click Roast on that new top row, then close the Roast window.

Expected: the Roast window showed a recommended model and issues, and the row's button now reads
View roast.

## W5: Don't flag real work

1. Set Routing level to Balanced and turn Use recommended model on.
2. Enter "Design a multi-region failover architecture for a payments ledger. Compare consistency
   models and list the failure modes." and click Run this prompt.

Expected: the new row is on Opus 5.5 with status OK.

## W7: Move the routing level

1. Make sure Use recommended model is off and set Routing level to Fastest.
2. Enter "Summarize this meeting transcript." and click Run this prompt.
3. Set Routing level to Full power and click Run this prompt again.

Expected: of the two new rows, the older is on Opus 5.5 with status Overkill and the newer is on
Opus 5.5 with status OK.

## U1: Manage users

Opens straight on User management (`/#users`).

1. In Add a user, enter a new username such as "Barbara" plus four digits, team "Core", Team
   access, and click Create user and token.

Expected: a token box appears and the new user is listed with team Core and Team access.

## U2: Make a demo login

1. Click Sign out, then Demo, create new token.
2. Enter a new username such as "demo" plus four digits and a password of at least 8 characters,
   leave Team and Access as they are, click Create login and token, then Continue.

Expected: the page says it is signed in as the new username, on team Demo, with Self access.

## E1: Bad input

1. Clear the Prompt box and click Run this prompt.

Expected: the page shows "Enter a prompt before sending." and no new row appears.

## W6: First-time visitor (checked by hand)

Open the app signed out. Expected: it asks you to sign in and says what the product does. Seldon
signs in first, so this one can't run there.

## Automated only

`python -m pytest` covers the rest: the retry-loop stop (W3), the developer leaderboard (W8) and
Reset demo (E4), which left the page with their controls, plus E2 upstream failures, E3
unauthorized proxy use, U1 cost math, U2 rule edges, streaming, Jev fallbacks and model swap
safeguards.
