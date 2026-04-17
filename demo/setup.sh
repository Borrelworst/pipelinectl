#!/usr/bin/env bash
# Sourced by demo/demo.tape to set up PATH and prompt before recording.
chmod +x demo/mock/pipelinectl 2>/dev/null
export PATH="$(pwd)/demo/mock:$PATH"
export PS1='❯ '
