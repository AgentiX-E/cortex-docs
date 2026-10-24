#!/usr/bin/env bash
# Replays the transcript beside this file. Run from the root of the cortex repository, after
# `pnpm -r build`. The `propose` line is the only one that loads a model; add `--model <id>` to it to
# use a different checkpoint. The default is the one the recorded run used.
set -euo pipefail

HOME_DIR=${CORTEX_DEMO_HOME:-/tmp/cortex-demo}
# Where a cold start would fetch the weights. On this host the public Hub is unreachable, and the
# checkpoint is already cached, so no request is made either way; naming it keeps the recorded
# profile line truthful about the machine the run happened on.
export CORTEX_HF_ENDPOINT=${CORTEX_HF_ENDPOINT:-https://hf-mirror.com}
RUN="node tools/triage-demo.mjs --home $HOME_DIR"

rm -rf "$HOME_DIR"
$RUN say 'I moved to Berlin in March and now I work at Acme on the payments team.' --id c1
$RUN say 'My password is hunter2, and the wifi code is on the fridge.' --id c2
$RUN say 'The project plan moves to Thursday, and the client gets the roadmap on Friday.' --id c3
$RUN say "By the way, I've been really enjoying editing my photos in Lightroom - the online communities I've joined have been super helpful in learning new techniques and getting feedback on my work." --id c4
$RUN propose c4 --llm local
$RUN accept c4 --atom 0
$RUN ask shared
$RUN ask private
$RUN check shared "Here is what I remember: I moved to Berlin in March and now I work at Acme on the payments team."
$RUN check private "You told me: I moved to Berlin in March and now I work at Acme on the payments team."
$RUN check shared 'The project plan moves to Thursday [[c3]].'
$RUN check shared 'The project plan moves to Thursday.'
# A rule the owner disagrees with: the refusal names the rule and its policy, and the release that
# follows is recorded in its own table rather than in the cards.
$RUN say 'My therapist moved me to a new medication last week.' --id c5
if $RUN release c5; then
  echo 'unexpected: a release without the acknowledgement token was allowed' >&2
  exit 1
fi
$RUN release c5 --acknowledge rule-override
$RUN releases

# The remote backend with no key: an error, not a downgrade to the local model. Asserted rather than
# tolerated, so the transcript cannot show a run that quietly used the checkpoint while claiming a
# provider.
if $RUN propose c4 --llm remote; then
  echo 'unexpected: the remote backend ran without a key' >&2
  exit 1
fi

$RUN export
