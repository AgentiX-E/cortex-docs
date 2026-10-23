#!/usr/bin/env bash
# Replays the transcript beside this file. Run from the root of the cortex repository, after
# `pnpm -r build`. The `propose` line is the only one that loads a model; add `--model <id>` to it to
# use a different checkpoint. The default is the one the recorded run used.
set -euo pipefail

HOME_DIR=${CORTEX_DEMO_HOME:-/tmp/cortex-demo}
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
$RUN export
