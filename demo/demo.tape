# pipelinectl terminal demo
# Run from repo root: vhs demo/demo.tape
# Requires: brew install vhs
#
# This uses demo/mock/pipelinectl — a shell script that mimics the real tool's
# output so the demo works without a live Azure DevOps connection.

Output demo/demo.gif

Set Theme "Catppuccin Mocha"
Set FontSize 14
Set Width 1200
Set Height 600
Set Padding 20
Set CursorBlink false
Set TypingSpeed 50ms

# Silent setup: point PATH to our mock and set a clean prompt
Hide
Type "source demo/setup.sh && clear"
Enter
Sleep 500ms
Show

Sleep 1000ms

# 1. Show available pipelines
Type "pipelinectl list"
Sleep 300ms
Enter
Sleep 2000ms

# 2. Push branch and trigger pipeline with live log streaming
Sleep 800ms
Type "pipelinectl push-run build-and-test --logs"
Sleep 300ms
Enter
Sleep 10000ms
