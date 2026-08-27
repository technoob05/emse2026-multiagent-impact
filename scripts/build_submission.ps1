param(
    [switch]$RunFullAnalysis
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$manuscriptDir = Join-Path $projectRoot "paper\manuscript"
$pdfOutputDir = Join-Path $projectRoot "build\pdf"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$CommandArgs
    )
    & $Executable @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed with exit code $LASTEXITCODE"
    }
}

function Assert-ProjectFile {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath
    )
    $resolvedPath = Join-Path $projectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) {
        throw "Missing required build input: $resolvedPath"
    }
}

function Build-LaTeXDocument {
    param(
        [Parameter(Mandatory = $true)][string]$BaseName
    )

    Assert-ProjectFile "paper\manuscript\$BaseName.tex"
    Invoke-Checked pdflatex -interaction=nonstopmode -halt-on-error "$BaseName.tex"
    Invoke-Checked bibtex $BaseName
    Invoke-Checked pdflatex -interaction=nonstopmode -halt-on-error "$BaseName.tex"
    Invoke-Checked pdflatex -interaction=nonstopmode -halt-on-error "$BaseName.tex"
    # sn-jnl can need one additional pass from a clean directory to stabilize
    # title-page anchors and cross-references.
    Invoke-Checked pdflatex -interaction=nonstopmode -halt-on-error "$BaseName.tex"

    $latexLog = Join-Path $manuscriptDir "$BaseName.log"
    $bibtexLog = Join-Path $manuscriptDir "$BaseName.blg"
    $latexProblems = Select-String -LiteralPath $latexLog -Pattern @(
        "LaTeX Error",
        "Citation .* undefined",
        "Reference .* undefined",
        "There were undefined references",
        "Rerun to get cross-references right",
        "Label\(s\) may have changed",
        "Overfull \\[hv]box",
        "destination with the same identifier",
        "duplicate ignored",
        "Emergency stop",
        "Fatal error"
    ) -CaseSensitive:$false
    if ($latexProblems) {
        $details = ($latexProblems | ForEach-Object { $_.Line.Trim() }) -join [Environment]::NewLine
        throw "LaTeX validation failed for $BaseName.tex:`n$details"
    }

    $bibtexProblems = Select-String -LiteralPath $bibtexLog -Pattern @(
        "I couldn't open",
        "I found no",
        "Repeated entry",
        "error message"
    ) -CaseSensitive:$false
    if ($bibtexProblems) {
        $details = ($bibtexProblems | ForEach-Object { $_.Line.Trim() }) -join [Environment]::NewLine
        throw "BibTeX validation failed for $BaseName.tex:`n$details"
    }

    $compiledPdf = Join-Path $manuscriptDir "$BaseName.pdf"
    if (-not (Test-Path -LiteralPath $compiledPdf -PathType Leaf)) {
        throw "LaTeX did not create the expected PDF: $compiledPdf"
    }
}

Push-Location $projectRoot
try {
    Invoke-Checked uv sync

    if ($RunFullAnalysis) {
        Invoke-Checked $pythonExe scripts\analysis\run_exploration.py
        Invoke-Checked $pythonExe scripts\analysis\run_contributor_analysis.py
        Invoke-Checked $pythonExe scripts\analysis\run_streak_analysis.py
        Invoke-Checked $pythonExe scripts\analysis\run_direct_handoff_analysis.py
    }

    Invoke-Checked $pythonExe scripts\audit\profile_dataset_schema.py
    Invoke-Checked $pythonExe scripts\figures\visualize_dataset.py
    Invoke-Checked $pythonExe scripts\analysis\run_direct_continuity_analysis.py
    Invoke-Checked $pythonExe scripts\audit\build_human_audit_packets.py
    Invoke-Checked $pythonExe scripts\analysis\run_cross_agent_review_exploration.py
    Invoke-Checked $pythonExe scripts\analysis\run_feedback_landmark_models.py
    Invoke-Checked $pythonExe scripts\analysis\run_response_ownership_analysis.py
    Invoke-Checked $pythonExe scripts\analysis\run_response_ownership_robustness.py
    Invoke-Checked $pythonExe scripts\analysis\run_coordination_topology_analysis.py
    Invoke-Checked $pythonExe scripts\analysis\run_burst_collapsed_topology.py
    Invoke-Checked $pythonExe scripts\analysis\run_deep_coordination_transitions.py
    Invoke-Checked $pythonExe scripts\analysis\run_legacy_extension_ownership_persistence.py
    Invoke-Checked $pythonExe scripts\analysis\run_human_memory_bridge_analysis.py
    Invoke-Checked $pythonExe scripts\analysis\run_legacy_extension_repository_memory.py
    Invoke-Checked $pythonExe scripts\analysis\run_addressed_edge_landmark_analysis.py
    Invoke-Checked $pythonExe scripts\analysis\run_addressed_edge_specificity_analysis.py
    Assert-ProjectFile "scripts\analysis\run_addressed_edge_confounding_sensitivity.py"
    Invoke-Checked $pythonExe scripts\analysis\run_addressed_edge_confounding_sensitivity.py
    Assert-ProjectFile "scripts\analysis\run_addressed_edge_scope_audit.py"
    Invoke-Checked $pythonExe scripts\analysis\run_addressed_edge_scope_audit.py
    Assert-ProjectFile "scripts\analysis\run_rq3_extensions.py"
    Invoke-Checked $pythonExe scripts\analysis\run_rq3_extensions.py
    Assert-ProjectFile "scripts\analysis\run_task_context_interaction.py"
    Invoke-Checked $pythonExe scripts\analysis\run_task_context_interaction.py
    Assert-ProjectFile "scripts\analysis\run_merge_curves.py"
    Invoke-Checked $pythonExe scripts\analysis\run_merge_curves.py
    Assert-ProjectFile "scripts\analysis\run_anchorability_coverage.py"
    Invoke-Checked $pythonExe scripts\analysis\run_anchorability_coverage.py
    Assert-ProjectFile "scripts\analysis\run_burst_threshold_selection.py"
    Invoke-Checked $pythonExe scripts\analysis\run_burst_threshold_selection.py
    Assert-ProjectFile "scripts\analysis\run_pseudo_edge_negative_control.py"
    Invoke-Checked $pythonExe scripts\analysis\run_pseudo_edge_negative_control.py
    Assert-ProjectFile "scripts\analysis\run_user_account_automation_audit.py"
    Invoke-Checked $pythonExe scripts\analysis\run_user_account_automation_audit.py
    Assert-ProjectFile "scripts\analysis\run_addressed_edge_reply_content_audit.py"
    Invoke-Checked $pythonExe scripts\analysis\run_addressed_edge_reply_content_audit.py
    Assert-ProjectFile "scripts\analysis\run_heterogeneity_audit.py"
    Invoke-Checked $pythonExe scripts\analysis\run_heterogeneity_audit.py
    Assert-ProjectFile "scripts\analysis\run_worked_example.py"
    Invoke-Checked $pythonExe scripts\analysis\run_worked_example.py
    Assert-ProjectFile "scripts\analysis\run_confounder_benchmarks.py"
    Invoke-Checked $pythonExe scripts\analysis\run_confounder_benchmarks.py
    Assert-ProjectFile "scripts\analysis\run_matched_thread_position_audit.py"
    Invoke-Checked $pythonExe scripts\analysis\run_matched_thread_position_audit.py
    Invoke-Checked $pythonExe scripts\analysis\run_cross_corpus_attribution_sensitivity.py
    Invoke-Checked $pythonExe scripts\audit\prepare_feedback_response_audit.py
    Invoke-Checked $pythonExe scripts\audit\prepare_review_collision_audit.py
    Invoke-Checked $pythonExe scripts\analysis\run_collision_descriptive_extension.py
    Assert-ProjectFile "scripts\analysis\run_sample_flow.py"
    Invoke-Checked $pythonExe scripts\analysis\run_sample_flow.py
    Assert-ProjectFile "scripts\reporting\generate_technical_appendix_tables.py"
    Invoke-Checked $pythonExe scripts\reporting\generate_technical_appendix_tables.py
    Invoke-Checked $pythonExe scripts\validation\validate_response_ownership_outputs.py
    Invoke-Checked $pythonExe scripts\validation\validate_coordination_extension_outputs.py
    Assert-ProjectFile "scripts\figures\visualize_manuscript_figures.py"
    Invoke-Checked $pythonExe scripts\figures\visualize_manuscript_figures.py
    Invoke-Checked uv run --with pytest python -m pytest -q
    Invoke-Checked $pythonExe scripts\reporting\build_handoff_notebook.py
    Invoke-Checked $pythonExe scripts\reporting\execute_notebook.py notebooks\02_artifact_handoff_exploration.ipynb

    foreach ($index in 1..6) {
        Assert-ProjectFile "build\figures\Fig${index}_v2.pdf"
    }
    Assert-ProjectFile "outputs\figures\dataset_schema_and_joins.pdf"
    Assert-ProjectFile "outputs\figures\anchorable_channel_coverage.pdf"
    Assert-ProjectFile "outputs\figures\burst_threshold_sensitivity.pdf"
    foreach ($index in 1..6) {
        Copy-Item (Join-Path $projectRoot "build\figures\Fig${index}_v2.pdf") (Join-Path $manuscriptDir "Fig${index}.pdf") -Force
    }
    Copy-Item outputs\figures\dataset_schema_and_joins.pdf paper\manuscript\FigS1.pdf -Force
    Copy-Item outputs\figures\anchorable_channel_coverage.pdf paper\manuscript\FigS2.pdf -Force
    Copy-Item outputs\figures\burst_threshold_sensitivity.pdf paper\manuscript\FigS3.pdf -Force

    Push-Location $manuscriptDir
    try {
        Build-LaTeXDocument "main"
        Build-LaTeXDocument "technical_appendix"
    }
    finally {
        Pop-Location
    }

    # The page counts quoted in the readiness and validation documents are
    # read from the PDFs that were just built, so they cannot drift.
    Assert-ProjectFile "scripts\release\sync_page_counts.py"
    Invoke-Checked $pythonExe scripts\release\sync_page_counts.py

    New-Item -ItemType Directory -Path $pdfOutputDir -Force | Out-Null
    Copy-Item paper\manuscript\main.pdf build\pdf\emse_multiagent_submission_draft.pdf -Force
    Copy-Item paper\manuscript\technical_appendix.pdf build\pdf\emse_multiagent_technical_appendix.pdf -Force
    & (Join-Path $PSScriptRoot "package_submission.ps1")
    Write-Host "Built build\pdf\emse_multiagent_submission_draft.pdf"
    Write-Host "Built build\pdf\emse_multiagent_technical_appendix.pdf"
}
finally {
    Pop-Location
}
