# Optional PortBridge pull request summary

Maintainers can add a job that searches for prior work when someone opens or updates a pull request. It lists relevant catalog cards, possible matches, and a first check when one is available. Open the workflow run under **Actions** to read the job summary. The result is advisory and can be incomplete.

Add this file to the repository where the summary should appear, for example `.github/workflows/portbridge-summary.yml`. The example pins a PortBridge revision containing the tested action. Keep the job optional in branch protection. [Pinning actions to a commit](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions)

```yaml
name: PortBridge prior work

on:
  pull_request:
    types: [opened, reopened, synchronize, edited]

permissions: {}

jobs:
  prior-work:
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - name: Add prior-work links to Job Summary
        continue-on-error: true
        uses: akimfomin/PortBridge@892d9be1e33ec9eaa9a3758ba42cdd5bb1519128
```

The action reads the title and GitHub PR URL from `GITHUB_EVENT_PATH`. It uses those values locally against PortBridge's public JSON snapshot. The snapshot fetch does not include the title or PR URL. The job uses the runner's Python 3.10 or newer and needs no secrets, repository checkout, or installed Python packages. It writes only to `GITHUB_STEP_SUMMARY`. If the snapshot cannot be read, the summary tells the reviewer to continue the usual review. [Composite action metadata](https://docs.github.com/en/actions/reference/workflows-and-actions/metadata-syntax#runs-for-composite-actions) · [GitHub job summaries](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)

Use `pull_request` as shown. The action works with a public GitHub PR URL and declines other event types. Keep any unrelated workflow that runs contributor code separate from this job. For external contributions, GitHub may require a maintainer to approve running the workflow. [GitHub pull request events and forks](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)

To remove the integration, remove the workflow file from the repository that enabled it.
