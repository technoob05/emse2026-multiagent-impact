[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Archive,

    [string]$Metadata = "zenodo.json.example",

    [switch]$ValidateOnly,

    [switch]$Production,

    [switch]$Publish,

    [string]$PublishConfirmation = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
    throw "Archive not found: $Archive"
}
if (-not (Test-Path -LiteralPath $Metadata -PathType Leaf)) {
    throw "Metadata file not found: $Metadata"
}

if ($Publish -and $PublishConfirmation -cne "PUBLISH-IMMUTABLE-ZENODO-RECORD") {
    throw "Publishing is public and cannot be undone. Pass -PublishConfirmation PUBLISH-IMMUTABLE-ZENODO-RECORD."
}

$baseUrl = if ($Production) {
    "https://zenodo.org"
} else {
    "https://sandbox.zenodo.org"
}

$metadataObject = Get-Content -LiteralPath $Metadata -Raw -Encoding utf8 |
    ConvertFrom-Json

if ($metadataObject.publication_date -eq "REPLACE-WITH-YYYY-MM-DD") {
    $metadataObject.publication_date = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
}

foreach ($required in @("title", "description", "upload_type", "publication_date", "creators")) {
    if ($null -eq $metadataObject.$required) {
        throw "Zenodo metadata is missing required field: $required"
    }
    if ($required -eq "creators") {
        if (@($metadataObject.creators).Count -eq 0) {
            throw "Zenodo metadata must contain at least one creator."
        }
    } elseif ([string]::IsNullOrWhiteSpace([string]$metadataObject.$required)) {
        throw "Zenodo metadata is missing required field: $required"
    }
}

$archiveItem = Get-Item -LiteralPath $Archive

if ($ValidateOnly) {
    [ordered]@{
        valid = $true
        environment = if ($Production) { "production" } else { "sandbox" }
        archive_name = $archiveItem.Name
        archive_bytes = $archiveItem.Length
        archive_sha256 = (Get-FileHash -LiteralPath $archiveItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        title = $metadataObject.title
        publication_date = $metadataObject.publication_date
        creator_count = @($metadataObject.creators).Count
    } | ConvertTo-Json
    exit 0
}

$token = [Environment]::GetEnvironmentVariable("ZENODO_ACCESS_TOKEN", "Process")
if ([string]::IsNullOrWhiteSpace($token)) {
    throw "Set a newly rotated token in the process-scoped ZENODO_ACCESS_TOKEN environment variable."
}

$headers = @{
    Authorization = "Bearer $token"
}
$jsonHeaders = @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
}

$deposition = Invoke-RestMethod `
    -Uri "$baseUrl/api/deposit/depositions" `
    -Method Post `
    -Headers $jsonHeaders `
    -Body "{}"

$depositionId = [string]$deposition.id
$draftUrl = [string]$deposition.links.html

try {
    $escapedName = [Uri]::EscapeDataString($archiveItem.Name)
    $uploadUri = "$($deposition.links.bucket)/$escapedName"

    Invoke-WebRequest `
        -Uri $uploadUri `
        -Method Put `
        -Headers $headers `
        -InFile $archiveItem.FullName `
        -ContentType "application/zip" |
        Out-Null

    $metadataBody = @{
        metadata = $metadataObject
    } | ConvertTo-Json -Depth 20

    $updated = Invoke-RestMethod `
        -Uri "$baseUrl/api/deposit/depositions/$depositionId" `
        -Method Put `
        -Headers $jsonHeaders `
        -Body $metadataBody

    $receipt = [ordered]@{
        environment = if ($Production) { "production" } else { "sandbox" }
        deposition_id = $depositionId
        draft_url = $draftUrl
        archive_name = $archiveItem.Name
        archive_bytes = $archiveItem.Length
        archive_sha256 = (Get-FileHash -LiteralPath $archiveItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        reserved_doi = $updated.metadata.prereserve_doi.doi
        published = $false
    }

    if ($Publish) {
        $published = Invoke-RestMethod `
            -Uri "$baseUrl/api/deposit/depositions/$depositionId/actions/publish" `
            -Method Post `
            -Headers $headers
        $receipt.published = $true
        $receipt.record_url = $published.links.record_html
        $receipt.doi = $published.doi
    }

    $receipt | ConvertTo-Json -Depth 10
} catch {
    Write-Error "Zenodo operation failed after draft creation. Inspect or discard the draft at $draftUrl. $($_.Exception.Message)"
}
