# VECTOR read-only Bash guard for the vector-adversarial-reviewer subagent.
#
# Input : hook JSON on stdin (tool_input.command).
# Output: exit 2 + reason on stderr = BLOCK. exit 0 = allow.
# Policy: a single simple read-only git inspection command and nothing else:
#         git [--no-pager] status|diff|log|show|rev-parse|grep|ls-files|blame|cat-file|diff-tree|shortlog
#         No chaining, pipes, redirects, substitution, or git -c / --output.
# Safety: read-only; never runs the command. Fail-closed on unparseable input.
# Keep ASCII-only: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.

$ErrorActionPreference = 'Stop'

try {
    $raw = [Console]::In.ReadToEnd()
    $payload = $raw | ConvertFrom-Json
    $cmd = [string]$payload.tool_input.command
} catch {
    [Console]::Error.WriteLine('VECTOR reviewer guard: could not parse hook input; blocking (fail-closed).')
    exit 2
}

$c = $cmd.Trim()
$allowed = '^git (--no-pager )?(status|diff|log|show|rev-parse|grep|ls-files|blame|cat-file|diff-tree|shortlog)( |$)'

if ($c -cmatch '[;&|<>`$(){}\r\n]' -or $c -cmatch '--output' -or $c -cnotmatch $allowed) {
    [Console]::Error.WriteLine('BLOCKED: the vector-adversarial-reviewer is read-only. Only a single simple git inspection command is allowed (status, diff, log, show, rev-parse, grep, ls-files, blame, cat-file, diff-tree, shortlog). Use the Read/Grep/Glob tools for file inspection.')
    exit 2
}

exit 0
