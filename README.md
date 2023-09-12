# Review App Scan

This is a script intended to be used within Actions workflows that will scan the kubernetes cluster  set as your current context for review apps that are older than a specified time. This script will not actually detroy any namespaces or review apps, but produce a file that can can be used in a Github Actions matrix.

It replaces the fragile Bash scripting used in the `review-app-scan` Actions workflow.

## Requirements

- Poetry
- Helm CLI
- Valid Kube config for the intended cluster

## Usage

1. Install the dependences with `poetry install`
2. Run with `poetry run scan <review app name>`. The review app name will be the last part of the namespaces, for example `casebook` or `energy-comparison-table`
3. Once run, the script will output a file called `GITHUB_OUTPUT`. This will be picked up by the Actions runner and can be used as the input for another steps matrix, for example:

```yaml
  trigger_destroy:
    if: needs.review-app-scan.outputs.matrix != '{"pr_numbers":[]}'
    needs: review-app-scan
    secrets: inherit
    strategy:
      matrix: ${{ fromJson(needs.review-app-scan.outputs.matrix) }}
      fail-fast: false
    uses: ./.github/workflows/review-app-destroy.yml
    with:
      pr_number: ${{ matrix.pr_numbers }}
```

The above example job will trigger the `review-app-destroy` workflow for each of the outdated review apps, passing in a PR number for each one.

## Arguments

```text
usage: __main__.py [-h] [--max-age MAX_AGE] [--debug] review_app_name

positional arguments:
  review_app_name

options:
  -h, --help         show this help message and exit
  --max-age MAX_AGE  Max time since a review app was updated in hours
  --debug, -d        Pringt debug info
```
