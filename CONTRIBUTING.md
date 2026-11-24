# Contributing to PortBridge

PortBridge helps independent Xbox Series compatibility teams share fixes and evidence. You can contribute from any project and keep the discussion in the repository where the work belongs.

## Share a result

1. Search by the exact error, shader instruction, or PR number. Open the original links and check their revisions and scope. [Search PortBridge](https://akimfomin.github.io/PortBridge/)
2. Choose a test you can reproduce. Record the project and exact commit, platform and graphics backend, test input, expected result, actual result, and limits.
3. Submit one report with its original source and attribution. Include negative findings if they will save another team a repeat investigation. [Evidence form](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml)
4. If it helps a second project, post the link in the relevant existing issue or PR with a specific proposed check or patch. Keep the resulting decision or change linked from the report.

Public source links and synthetic fixtures are welcome. Keep game assets, credentials, and private logs out of contributions.

## Review or pick up work

Check the current work and its sources before starting. Distinguish an author's report, a CI result, a source inspection, and an independent reproduction. Check both the receiving project and the exact revision before calling a result transferable. [Porting work log](docs/PORTING-WORK.md)

For code changes to PortBridge, read [AGENTS.md](AGENTS.md), keep the change scoped, and run `python -m unittest discover -s tests -v`. For workflow suggestions, describe the current friction and what a useful result would look like. [Suggest an improvement](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml)
