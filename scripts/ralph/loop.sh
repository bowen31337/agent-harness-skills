#!/bin/bash
set -euo pipefail

# Autonomous Agent Loop — runs Claude Code iterations until all stories pass
# Usage: ./scripts/ralph/loop.sh [max_iterations]

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

MAX_ITERATIONS="${1:-15}"
ITERATION=0

echo "=== Autonomous Agent Loop ==="
echo "Project: $PROJECT_ROOT"
echo "Max iterations: $MAX_ITERATIONS"
echo ""

while [ "$ITERATION" -lt "$MAX_ITERATIONS" ]; do
    ITERATION=$((ITERATION + 1))
    echo "--- Iteration $ITERATION / $MAX_ITERATIONS ---"

    # Check if all stories pass
    REMAINING=$(python3 -c "
import json
with open('prd.json') as f:
    prd = json.load(f)
remaining = [s for s in prd['userStories'] if not s['passes']]
print(len(remaining))
")

    if [ "$REMAINING" -eq 0 ]; then
        echo "<promise>COMPLETE</promise>"
        echo "All stories pass! Loop complete after $ITERATION iterations."
        exit 0
    fi

    echo "$REMAINING stories remaining."

    # Get next story
    NEXT_STORY=$(python3 -c "
import json
with open('prd.json') as f:
    prd = json.load(f)
for s in prd['userStories']:
    if not s['passes']:
        print(s['id'] + ': ' + s['title'])
        break
")

    echo "Next story: $NEXT_STORY"

    # Run Claude Code on the next story
    claude -p "You are implementing stories from prd.json in $(pwd).

Read prd.json and progress.txt first. Find the next story that has passes=false.
Implement ONLY that one story following its acceptance criteria exactly.

After implementation:
1. Run: PYTHONPATH=. .venv/bin/python -m pytest tests/ -o 'addopts=' -q --ignore=tests/browser --ignore=tests/gates/test_agents_md_token.py 2>&1 | tail -5
2. If tests pass, update prd.json to set passes=true for the completed story
3. Update progress.txt with what you did
4. If tests fail, fix the issues before marking as done

Key patterns:
- Tests: PYTHONPATH=. .venv/bin/python -m pytest <file> -o 'addopts=' -q
- Templates: harness_skills/templates/
- Models: harness_skills/models/
- Gates: harness_skills/gates/principles.py

Do NOT modify files outside the scope of the current story.
Do NOT skip acceptance criteria.
" --allowedTools 'Edit,Write,Read,Bash,Glob,Grep' 2>&1 | tail -20

    echo "Iteration $ITERATION complete."
    echo ""
done

echo "Max iterations reached ($MAX_ITERATIONS). Some stories may still be incomplete."
exit 1
