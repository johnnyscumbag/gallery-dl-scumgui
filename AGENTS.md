# ScumGUI — Agent Instructions

## 1. Project Overview

ScumGUI is a portable Windows GUI frontend for `gallery-dl`.

The canonical repository is:

- GitHub: `johnnyscumbag/gallery-dl-scumgui`

GitHub is the source of truth. Other repositories, including any GitLab mirror, must follow the canonical GitHub repository.

Preserve the application's existing architecture, established UI conventions, portable behaviour, settings persistence, and download functionality.

## 2. General Development Workflow

Work autonomously on the task requested by the user, from investigation through implementation, testing, version control, and reporting.

For each task:

1. Inspect the relevant source code and existing project instructions.
2. Check the current Git branch, working-tree status, and recent commits.
3. Identify the smallest appropriate implementation that solves the requested problem.
4. Implement the change without unrelated refactoring.
5. Run relevant tests, validation, and build checks.
6. Review the final diff for regressions, accidental changes, and unrelated files.
7. Commit successful changes using a descriptive commit message.
8. Push the commit to the canonical GitHub repository when the task is complete and the environment permits it.
9. Verify the resulting commit and push status.
10. Report the outcome clearly.

Do not stop after editing files when the requested task can reasonably be completed, tested, committed, and pushed in the current environment.

Do not ask the user to approve routine implementation steps when the configured permissions already allow them.

If an action is blocked by a permission boundary, missing credential, unavailable tool, or other environmental restriction, explain the specific blocker and request only the intervention necessary to continue.

Never claim that a test, build, commit, or push succeeded unless it actually did.

## 3. Git Safety and Versioning

Git is the version history and recovery mechanism for ScumGUI.

### Before making changes

- Run `git status --short --branch`.
- Confirm the current branch and repository remotes.
- Inspect recent commits when relevant.
- Preserve any existing user changes.
- Do not overwrite, discard, reset, or incorporate unrelated changes without understanding their purpose.

### Commits

- Create one commit for each logically complete, tested change.
- Use concise, descriptive commit messages.
- Prefer imperative messages, such as:
  - `Hide skipped output from activity panel`
  - `Persist download queue across restarts`
  - `Prevent duplicate application instances`
- Do not create empty commits.
- Do not commit secrets, credentials, personal data, local caches, build artifacts, or generated files that are not intended to be version-controlled.
- Follow the repository's existing `.gitignore` and commit conventions.

### Codex co-author attribution

- For commits where Codex makes a substantial implementation contribution, retain the repository's configured Git author identity and add this exact trailer as the final line of the commit message, separated from the subject and body by a blank line:
  - `Co-authored-by: Codex <noreply@openai.com>`
- Do not add the trailer to trivial, mechanical, or documentation-only changes where Codex did not materially contribute.
- Do not change Git author or committer configuration to attribute Codex contributions.

### Pushes

- Push completed commits to the canonical GitHub repository after relevant checks pass.
- Use the existing branch and remote configuration unless the task requires a deliberate change.
- Verify that the push succeeded and that the remote contains the expected commit.
- If a push fails, diagnose the reason where possible and report the exact blocker.
- Never report a local commit as if it were already published remotely.

### Destructive operations

Never perform any of the following without explicit user approval:

- Force-push.
- Rewrite published Git history.
- Delete remote branches or tags.
- Run destructive resets or discard user changes.
- Remove repository history.
- Replace or delete the canonical repository.
- Change repository visibility or security settings.

Prefer small, reversible commits over risky bulk changes.

## 4. Testing and Build Validation

Choose checks appropriate to the files and functionality changed.

- Run relevant existing automated tests.
- Run Python syntax or compilation checks when Python code changes.
- Run the Windows application build when the change could affect packaging, dependencies, resources, or runtime behaviour.
- Validate configuration files when they change.
- Check UI-related behaviour where practical.
- Inspect test output and exit codes rather than assuming success.
- Fix regressions introduced by the change before committing.

Do not claim that the complete application works merely because a syntax check passed.

If a test or build cannot be run, explain why and distinguish completed checks from checks that remain outstanding.

Avoid unrelated dependency upgrades, broad refactoring, and changes to the build pipeline unless required by the task.

## 5. UI and Design Conventions

Preserve ScumGUI's established visual identity.

- Use the existing Fusion-based Qt interface and established dark styling.
- Prefer a clean, flat appearance with subtle hover effects.
- Keep spacing, typography, controls, icons, and colours consistent with surrounding UI elements.
- Use clear and semantically appropriate status indicators.
- Reserve warning and error symbols for actual warnings and errors.
- Use neutral indicators for ordinary states such as skipped files.
- Avoid unnecessary visual clutter, decorative elements, or inconsistent icon styles.
- Preserve existing functionality and accessibility when modifying the interface.

Do not redesign unrelated parts of the application when fixing a specific UI issue.

## 6. Application Behaviour and Persistence

Preserve the application's portable Windows behaviour and existing user data.

- Keep user settings persistent across application restarts.
- Respect the existing settings and configuration locations.
- Preserve the current queue persistence behaviour and its established storage location.
- Avoid silently changing configuration formats or locations.
- Handle missing, invalid, or outdated configuration files safely.
- Avoid overwriting existing settings when applying defaults or migrations.
- Preserve active downloads and queued items when modifying queue management.
- Make stop, cancel, skip, and error states clear and consistent.
- Prevent duplicate application instances when required by the existing design, while preserving intended ways to submit additional URLs to the running instance.

Before changing persistence or migration behaviour, inspect the existing implementation and tests. Do not assume that data is stored beside the executable.

## 7. gallery-dl Integration

Preserve compatibility with the application's intended `gallery-dl` workflow.

- Respect the existing configuration and download-directory behaviour.
- Preserve the intended separation of image downloads into `Photos` and video downloads into `Videos`.
- Avoid introducing unwanted nested directory structures.
- Preserve the configured skip behaviour and avoid redownloading existing files unnecessarily.
- Keep the bundled `gallery-dl` executable and its update mechanism consistent with the existing project design.
- Do not silently change extraction, download, or file-classification behaviour when making unrelated UI changes.

Verify the relevant configuration and runtime behaviour when modifying the download pipeline.

## 8. GitHub Actions and Releases

GitHub is the canonical source repository.

- Preserve existing GitHub Actions workflows unless a change is required.
- Inspect workflow behaviour before modifying build, packaging, release, or publishing automation.
- Keep Windows builds reproducible.
- Avoid unnecessary workflow changes that could consume CI minutes or generate redundant builds.
- Check workflow results after pushing when the relevant status is available.
- Distinguish a successful Git push from a successful CI build or release.
- Do not publish a release or create a tag unless the task or existing release process calls for it.

## 9. GitLab Mirror

If the GitLab mirror workflow is configured, GitHub remains the source of truth.

- Push normal development changes to GitHub only.
- Allow the established GitHub Actions workflow to mirror changes to GitLab.
- Do not make independent development commits on the mirror unless explicitly requested.
- Preserve branches, tags, and repository history as required by the mirror workflow.
- Never expose, print, commit, or otherwise disclose mirror credentials or tokens.
- If mirroring fails, report the failure separately from the GitHub push result.

Do not assume the mirror workflow exists or is functioning; inspect the repository before relying on it.

## 10. Security and Dependencies

- Never hardcode credentials, API keys, passwords, or access tokens.
- Never print secret values into logs or chat.
- Avoid unnecessary network access and external downloads.
- Use existing dependencies when practical.
- Explain the reason for any new dependency.
- Do not disable security controls to make a build or test pass.
- Keep changes within the permissions and workspace boundaries configured for the session.

## 11. Scope and Communication

- Keep each change focused on the user's request.
- Ask a clarifying question only when an important ambiguity prevents a safe or correct implementation.
- Do not ask for confirmation of routine steps already authorised by the user.
- Do not silently make unrelated improvements.
- Report blockers promptly rather than repeatedly attempting an operation that requires user intervention.

When the user requests an implementation, aim to deliver the completed change rather than merely suggesting code or instructions.

## 12. Completion Report

At the end of each task, provide a concise report containing:

- **Implemented:** What changed.
- **Files changed:** The important modified files.
- **Validation:** Tests, syntax checks, and builds actually performed, with their results.
- **Commit:** The commit hash and message, if committed.
- **Push:** Whether the commit was successfully pushed to GitHub.
- **CI and mirror:** Relevant workflow or mirror results, when available.
- **Remaining issues:** Any failures, limitations, or checks still outstanding.

Clearly distinguish local changes, committed changes, pushed changes, and published releases.

A task is not fully complete merely because the code was edited. Complete as much of the implementation, validation, versioning, and publishing workflow as the available environment permits.
