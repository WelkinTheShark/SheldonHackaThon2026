# Wren use-case tests

Paste each test into Wren, pointed at the deployed URL. W1 and W2 are the two required core
workflows. Runs cost $3 each after the first 10, so run W1 and W2 most and the others once.

The final W1 and W2 runs must be against the final build, with real Claude calls, so Simulated
responses must be off. Rehearsal runs can use it, and their rows are marked Simulated.
Expected results check labels and amounts, never Claude's wording, because replies vary.

**Sign-in.** The page asks for a username and password. Create a demo login with all access first,
in the Users section or with `python -m app.devs add "wren" --team Demo --access all` and then
`python -m app.devs password "wren"`. Start every test with: "Open the app, enter wren as the
Username and <the password> as the Password, and click Sign in." Use a demo-only password, since it
is pasted into Wren. Each step below that says "Open the app" means after signing in.

## W1: Catch and fix overkill (required)

Task: A developer finds a wasteful call and stops it from happening again.

1. Open the app and click Reset demo.
2. Choose Opus 5.5 as the model.
3. Enter "Write a commit message for: fix typo in README" as the prompt and click Send call.
4. Turn on Use recommended model.
5. Click Send call again with the same prompt.

Expected:
- The first call appears in Live calls on Opus 5.5 with the status Overkill.
- The second call appears on Haiku 5.5 with the status Downshifted.
- Saved is more than $0.0000.

## W2: Enforce a budget (required)

Task: A team lead sets a limit and confirms calls stop at it.

1. Open the app and click Reset demo.
2. Click Edit budget, enter 0.0001, and click Save.
3. Enter "Write a commit message for: fix typo in README" as the prompt and click Send call.
4. Note the spent amount, then click Send call again.
5. Click Edit budget, enter 1, and click Save.
6. Click Send call again.

Expected:
- The second call appears with the status Blocked by budget.
- The spent amount does not change after the blocked call.
- The third call runs, with no Blocked by budget status on its row.

## W3: Stop a retry loop

1. Open the app and click Reset demo.
2. Click Simulate agent retry loop.

Expected:
- Three calls appear on Haiku 5.5.
- A fourth row appears with the status Loop stopped.
- Blocked shows 1 and Saved is more than $0.0000.

## W4: Roast a prompt

1. Open the app and click Reset demo.
2. Enter "You are an expert. Please summarize this. Please summarize this." as the prompt.
3. Click Roast this prompt.
4. Click Roast this prompt again.
5. Click the older run's heading in Roast results to open it.

Expected:
- The Roast results panel to the right of Live calls says 2 runs.
- The newest run is open and shows a score out of 100, at least one issue, a suggested fix, and a
  receipt naming the model and cost.
- The older run opens when clicked.

## W4c: Roast a call that already ran

1. Open the app and click Reset demo.
2. Click the Simple task example and click Send call.
3. In Live calls, click the Roast button on that call's row.

Expected:
- A run appears in Roast results with a score out of 100 and a suggested fix.
- The call's Roast button now shows the same score out of 100.

## W4b: Take or override the recommended model

1. Open the app and click Reset demo.
2. Choose Opus 5.5 as the model.
3. Enter "Write a commit message for: fix typo in README" as the prompt.
4. Click Roast this prompt.
5. Click Send call.
6. Choose Opus 5.5 as the model again, then click Roast this prompt.
7. Click Use Opus 5.5 anyway.

Expected:
- After step 4, the page recommends Haiku 5.5, the Model menu shows Haiku 5.5, and a Use Opus 5.5
  anyway button appears below Send call.
- The call from step 5 appears on Haiku 5.5 with the status OK.
- The call from step 7 appears on Opus 5.5 with the status Overkill.

## W5: Don't flag real work

1. Open the app and click Reset demo.
2. Turn on Use recommended model.
3. Choose Opus 5.5, click the Real design example, and click Send call.

Expected: The call appears on Opus 5.5 with the status OK, and not Overkill or Downshifted.

## W6: First-time visitor

1. Open the app with no other instructions.

Expected: Before signing in, the page asks for a token and says what the product does. After
signing in, it shows "No calls yet. Send one on the left." and makes it clear how to send a first
call.

## W7: Move the routing level

1. Open the app and click Reset demo.
2. Set Routing level to Fastest.
3. Choose Opus 5.5, enter "Summarize this meeting transcript." as the prompt, and click Send call.
4. Set Routing level to Full power and click Send call again.
5. Enter "git push origin main" as the prompt and click Send call.

Expected:
- The call from step 3 appears on Opus 5.5 with the status Overkill.
- The call from step 4 appears on Opus 5.5 with the status OK.
- The call from step 5 appears on Opus 5.5 with the status Overkill.

## W8: Compare developers

Create two developers first, in the Users section or with `python -m app.devs add`. This test uses
the names Ada and Grace.

1. Open the app and click Reset demo.
2. Choose Ada as the developer and Opus 5.5 as the model, then click the Simple task example.
3. Click Send call five times.
4. Choose Grace as the developer and Haiku 5.5 as the model.
5. Click Send call five times.

Expected:
- Each row in Live calls shows its developer, an Ideal model of Haiku 5.5, and a Used model.
- The Developer leaderboard ranks Grace first at 0.0% overuse, and Ada second with higher overuse.
- Each developer shows 5 prompts.

## U2: Make a demo login

1. Open the app without signing in.
2. Click Demo, create new token.
3. Enter a new username and a password of at least 8 characters, and click Create login and token.
4. Click Continue.

Expected:
- A dialog says the demo login is ready and shows a token and Claude Code settings.
- After Continue, the page says it is signed in as the new username, on team Demo, with Self access.

## U1: Manage users

1. Open the app. Scroll to Users.
2. Enter "Barbara" as the Username and "Core" as the Team, choose Team access, and click Create user
   and token.
3. Click New token on Barbara's row and accept the prompt.
4. Click Set in Barbara's Password column, enter a password of at least 8 characters, and click Save.

Expected:
- Barbara appears in the Users table with team Core and Team access.
- A token box shows a first token after step 2 and a different token after step 3.
- Barbara's Password column says Set.

## E1 and E4: Bad input and reset

1. Open the app and click Send call with an empty prompt.
2. Choose the Simple task example, click Send call, then click Reset demo.

Expected: The empty prompt shows "Enter a prompt before sending." with no new call. After reset,
spent shows $0.0000 and Live calls is empty.

## Automated only

`python -m pytest` covers the rest of the table: E2 upstream failures, E3 unauthorized proxy use,
U1 cost math and U2 rule edges. It also covers streaming, Jev fallbacks and model swap safeguards.
