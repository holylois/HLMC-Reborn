# Automatic lag evidence

The monitor uses Spark's existing background history. It never stops/cancels the profiler or replaces history
with a future-only sample. A profile request is the fixed console command `spark profiler open`.

## Trigger and limits

- One genuine server-thread warning reporting at least 5 seconds behind, or three warnings within ten minutes.
- Ignore the first five boot minutes and planned maintenance. Require current players or a successful nonempty
  status sample within the last three minutes. Recent presence is evidence of recent play, not proof that a
  player remained connected throughout a hitch.
- Private diagnostic notes: at most one successful alert per hour.
- Profile requests: at most one every 30 minutes, independent of the note cooldown. A pending profile link must
  be delivered before a new request replaces it. Failed FIFO requests retry no sooner than five minutes later.
- Persist the latest requested event timestamp so the same event cannot be requested twice. Reset recent-play
  and event markers across server invocations; preserve disk-warning state.
- Read at most 2,000 matching event records and 4,000 records while finding the resulting profile link.
  Journal-query and malformed-event failures stop the new event reader. Player chat cannot spoof the genuine
  `[Server thread/WARN]` prefix required by the event parser.

The existing monitor timer checks every two minutes. A snapshot contains the rolling history available when
Spark handles the request; these settings do not guarantee that every hitch has a complete sample. No cause
is established until a profile actually covers a reported stall. Alert cooldowns and rolling retention can
still exclude later events; do not claim lag is fixed by improved evidence collection.

## Privacy and operations

Only event times/durations enter the new state fields. Alerts and profile links use the private staff webhook,
with mentions disabled and no public diagnostic fallback. Spark uses its existing configured profile provider;
the new request limit changes possible snapshot frequency, not the provider or recorded data schema.

The monitor update requires separate deployment approval. Preserve the existing monitor state, pause its
timer while replacing the one script, wait for an active invocation to finish, verify exact bytes and resume
the timer. Code rollback must not restore older monitor state or restart Minecraft. Keep the previous script
and transaction receipt privately. Generated fixtures must never write to the live console or send messages.

Relevant Linux checks: `python server/ops/test-ops.py LagWatch StorageWatch`. The complete operations suite also
imports Linux deployment code; do not run it as a Windows-native harness.
