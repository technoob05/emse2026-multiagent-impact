$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$manuscriptDir = Join-Path $projectRoot "paper\manuscript"
$submissionRoot = Join-Path $projectRoot "build\submission"
$sourceDir = Join-Path $submissionRoot "emse_multiagent_coordination_draft"
$zipPath = Join-Path $submissionRoot "emse_multiagent_coordination_draft_source.zip"
$mainPdfPackage = Join-Path $submissionRoot "emse_multiagent_coordination_draft_manuscript.pdf"
$appendixPdfPackage = Join-Path $submissionRoot "emse_multiagent_coordination_draft_technical_appendix.pdf"
$manifestPath = Join-Path $sourceDir "PACKAGE_MANIFEST.sha256"
$portalDir = Join-Path $submissionRoot "emse_portal_staging"
$portalSourceZip = Join-Path $portalDir "manuscript_source.zip"
$portalMainPdf = Join-Path $portalDir "manuscript.pdf"
$portalEsmPdf = Join-Path $portalDir "ESM_1.pdf"
$portalManifest = Join-Path $portalDir "CHECKSUMS.sha256"

$sourceFiles = @(
    "main.tex",
    "technical_appendix.tex",
    "generated_appendix_tables.tex",
    "apx_tables_data.tex",
    "apx_tables_identity.tex",
    "apx_tables_cohorts.tex",
    "apx_tables_coverage.tex",
    "apx_tables_rq1.tex",
    "apx_tables_rq2.tex",
    "apx_tables_heterogeneity.tex",
    "apx_tables_rq3.tex",
    "apx_tables_specificity.tex",
    "apx_tables_external.tex",
    "apx_tables_task_context.tex",
    "apx_tables_quality.tex",
    "apx_tables_reproduction.tex",
    "references.bib",
    "sn-jnl.cls",
    "sn-basic.bst",
    "Fig1.pdf",
    "Fig2.pdf",
    "Fig3.pdf",
    "Fig4.pdf",
    "Fig5.pdf",
    "Fig6.pdf",
    "FigS1.pdf",
    "FigS2.pdf",
    "README.md"
)

$sourceItems = foreach ($name in $sourceFiles) {
    $source = Join-Path $manuscriptDir $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing submission source file: $source"
    }
    [pscustomobject]@{ Name = $name; Path = $source }
}

# Editorial Manager should receive the manuscript source and Supplementary
# Information as separate items. Keep only files needed to compile main.tex in
# this portal-facing, flat source archive.
$portalSourceFiles = @(
    "main.tex",
    "references.bib",
    "sn-jnl.cls",
    "sn-basic.bst",
    "Fig1.pdf",
    "Fig2.pdf",
    "Fig3.pdf",
    "Fig4.pdf",
    "Fig5.pdf",
    "Fig6.pdf"
)

$compiledPdf = Join-Path $projectRoot "build\pdf\emse_multiagent_submission_draft.pdf"
if (-not (Test-Path -LiteralPath $compiledPdf -PathType Leaf)) {
    throw "Missing compiled manuscript: $compiledPdf"
}
$compiledAppendixPdf = Join-Path $projectRoot "build\pdf\emse_multiagent_technical_appendix.pdf"
if (-not (Test-Path -LiteralPath $compiledAppendixPdf -PathType Leaf)) {
    throw "Missing compiled technical appendix: $compiledAppendixPdf"
}

$expectedFlatFiles = @(
    $sourceFiles
    "manuscript.pdf"
    "technical_appendix.pdf"
    "PACKAGE_MANIFEST.sha256"
)
if (Test-Path -LiteralPath $sourceDir -PathType Container) {
    $unexpectedItems = Get-ChildItem -LiteralPath $sourceDir | Where-Object {
        $_.PSIsContainer -or $_.Name -notin $expectedFlatFiles
    }
    if ($unexpectedItems) {
        $names = ($unexpectedItems | Select-Object -ExpandProperty Name) -join ", "
        throw "Unexpected stale items in flat submission folder (not removed automatically): $names"
    }
}

New-Item -ItemType Directory -Path $sourceDir -Force | Out-Null
foreach ($item in $sourceItems) {
    Copy-Item -LiteralPath $item.Path -Destination (Join-Path $sourceDir $item.Name) -Force
}
Copy-Item -LiteralPath $compiledPdf -Destination (Join-Path $sourceDir "manuscript.pdf") -Force
Copy-Item -LiteralPath $compiledPdf -Destination $mainPdfPackage -Force
Copy-Item -LiteralPath $compiledAppendixPdf -Destination (Join-Path $sourceDir "technical_appendix.pdf") -Force
Copy-Item -LiteralPath $compiledAppendixPdf -Destination $appendixPdfPackage -Force

# This manifest travels inside the source ZIP, so every listed path must also
# be an archive member. PDF deliverables have separate hashes in portal staging.
$manifestInputs = @($sourceFiles)
$manifestLines = foreach ($name in $manifestInputs) {
    $path = Join-Path $sourceDir $name
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $name"
}
Set-Content -LiteralPath $manifestPath -Value $manifestLines -Encoding UTF8

$archiveInputs = @($sourceFiles + "PACKAGE_MANIFEST.sha256") | ForEach-Object {
    Join-Path $sourceDir $_
}
Compress-Archive -LiteralPath $archiveInputs -DestinationPath $zipPath -Force

$portalExpectedFiles = @(
    "manuscript_source.zip",
    "manuscript.pdf",
    "ESM_1.pdf",
    "CHECKSUMS.sha256"
)
if (Test-Path -LiteralPath $portalDir -PathType Container) {
    $unexpectedPortalItems = Get-ChildItem -LiteralPath $portalDir | Where-Object {
        $_.PSIsContainer -or $_.Name -notin $portalExpectedFiles
    }
    if ($unexpectedPortalItems) {
        $names = ($unexpectedPortalItems | Select-Object -ExpandProperty Name) -join ", "
        throw "Unexpected stale items in portal staging folder (not removed automatically): $names"
    }
}

New-Item -ItemType Directory -Path $portalDir -Force | Out-Null
$portalArchiveInputs = $portalSourceFiles | ForEach-Object {
    Join-Path $manuscriptDir $_
}
Compress-Archive -LiteralPath $portalArchiveInputs -DestinationPath $portalSourceZip -Force
Copy-Item -LiteralPath $compiledPdf -Destination $portalMainPdf -Force
Copy-Item -LiteralPath $compiledAppendixPdf -Destination $portalEsmPdf -Force

$portalManifestLines = foreach ($path in @($portalSourceZip, $portalMainPdf, $portalEsmPdf)) {
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $(Split-Path -Leaf $path)"
}
Set-Content -LiteralPath $portalManifest -Value $portalManifestLines -Encoding UTF8

Write-Host "Packaged source: $zipPath"
Write-Host "Packaged manuscript PDF: $mainPdfPackage"
Write-Host "Packaged technical appendix PDF: $appendixPdfPackage"
Write-Host "Prepared flat folder: $sourceDir"
Write-Host "Prepared Editorial Manager staging: $portalDir"
