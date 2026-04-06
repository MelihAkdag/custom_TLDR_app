#!/bin/bash

# Navigate to the project directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/.." || exit

# Activate the virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the weekly pipeline and send the email
echo "Starting weekly TLDR pipeline at $(date)"

# If you installed the package via `pip install -e .` then you can run `tldr-feed` directly.
# Alternatively, you can use `python -m tldr_feed.cli`
tldr-feed run-weekly --email

echo "Finished pipeline at $(date)"
