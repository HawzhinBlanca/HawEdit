# Legacy Camera Contract EARS

- LC-1: WHEN the actual motion tracker cannot establish usable speaking evidence
  for the fixture's observed shots, THE integration test SHALL assert that
  absence and SHALL NOT treat detected/injected face boxes as speaker identity.
- LC-2: WHEN that input is requested under preview policy, THE pipeline SHALL
  label any retained preview as unverified/static rather than speaker-tracked,
  SHALL NOT claim completion, and SHALL retain actual measured private bytes.
- LC-3: WHEN that input is requested under production policy, THE pipeline SHALL
  refuse camera admission without substituting a crop or producing a review MP4.
- LC-4: WHEN this historical expectation is corrected, THE test suite SHALL
  preserve the original red evidence, source fixture, detector inputs, thresholds,
  QC/signing helper and hash constant, and SHALL retain positive known-evidence
  controls without claiming native identity accuracy.

Planned coverage: retain the collected legacy integration test and extend it
over preview/production; unchanged candidate framing and motion/layout controls.
These are proposed criteria, not passing results or a completion claim.
