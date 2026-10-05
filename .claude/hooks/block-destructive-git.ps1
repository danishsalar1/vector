# VECTOR PreToolUse guard: block destructive Git commands before they execute.
#
# Input : hook JSON on stdin (tool_input.command = the Bash/PowerShell command text).
# Output: exit 2 + reason on stderr = BLOCK. exit 0 = no opinion (normal permission flow).
# Safety: read-only. This script never runs git or modifies anything.
#         Fail-closed: if the hook input cannot be parsed, the command is blocked.
# Scope : matches the command TEXT, including text inside `bash -c "..."`. It is a
#         conservative text screen, so it can over-block (e.g. a commit message that
#         quotes a blocked command, or `git remote prune`). Over-blocking is intended;
#         run such a command yourself if it is genuinely needed.
# Keep ASCII-only: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.

$ErrorActionPreference = 'Stop'

try {
    $raw = [Console]::In.ReadToEnd()
    $payload = $raw | ConvertFrom-Json
    $cmd = [string]$payload.tool_input.command
} catch {
    [Console]::Error.WriteLine('VECTOR git guard: could not parse hook input; blocking (fail-closed).')
    exit 2
}

if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

# Normalize: drop quote characters (git 'push' --force), collapse whitespace/newlines.
$c = ($cmd -replace "['""`]", '') -replace '\s+', ' '

# "git" followed by anything that is not a command separator, then whitespace.
# [^;&|] keeps each match inside one simple command.
$g = '\bgit\b[^;&|]*?\s'

$rules = @(
    @{ Name = 'git reset --hard';
       Pattern = $g + 'reset\b[^;&|]*\s--hard\b' },
    @{ Name = 'git clean with force (-f/-fd/-fdx/--force)';
       Pattern = $g + 'clean\b[^;&|]*\s(--force\b|-[a-zA-Z]*f[a-zA-Z]*\b)' },
    @{ Name = 'git push --force / -f / --force-with-lease / +refspec';
       Pattern = $g + 'push\b[^;&|]*\s(--force(-with-lease|-if-includes)?\b|-[a-zA-Z]*f[a-zA-Z]*\b|\+\S)' },
    @{ Name = 'git branch -D';
       Pattern = $g + 'branch\b[^;&|]*\s-[a-zA-Z]*D[a-zA-Z]*\b' },
    @{ Name = 'git branch delete + force (-df/-fd/--delete --force)';
       Pattern = $g + 'branch\b[^;&|]*\s(-[a-zA-Z]*(d[a-zA-Z]*f|f[a-zA-Z]*d)[a-zA-Z]*\b|(--delete|-d)\b[^;&|]*\s(--force|-f)\b|(--force|-f)\b[^;&|]*\s(--delete|-d)\b)' },
    @{ Name = 'git reflog expire/delete';
       Pattern = $g + 'reflog\s+(expire|delete)\b' },
    @{ Name = 'git gc --prune / git prune';
       Pattern = $g + '(gc\b[^;&|]*\s--prune\b|prune\b)' },
    @{ Name = 'history rewrite (filter-branch / filter-repo / update-ref -d)';
       Pattern = $g + '(filter-branch\b|filter-repo\b|update-ref\b[^;&|]*\s-d\b)' }
)

foreach ($rule in $rules) {
    if ($c -cmatch $rule.Pattern) {
        [Console]::Error.WriteLine('BLOCKED by VECTOR git guard: ' + $rule.Name + '. Destructive Git is not permitted in this project. Ask the user to run it manually if it is truly required.')
        exit 2
    }
}

exit 0
