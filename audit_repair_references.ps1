Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ToolRoot = $PSScriptRoot
$MissionRoot = Join-Path $ToolRoot "mission_assets"
$InventoryPath = Join-Path $MissionRoot "reports\asset_inventory.json"
$MissingReportPath = Join-Path $MissionRoot "reports\missing_or_unusual_files.md"
$DatabaseRoot = Join-Path $ToolRoot "database"
$ReportsRoot = Join-Path $ToolRoot "reports"
$RepairedRoot = Join-Path $ToolRoot "repaired_assets"

$imageExts = @(".png", ".ase", ".aseprite", ".bmp", ".jpg", ".jpeg")
$tiledExts = @(".tmx", ".tmj", ".tsx")

function New-CleanDirectory($Path) {
  if (Test-Path -LiteralPath $Path) {
    Remove-Item -LiteralPath $Path -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Ensure-Directory($Path) {
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Normalize-AssetPath([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
  $p = [Uri]::UnescapeDataString($Path)
  $p = $p -replace '/', '\'
  $p = $p -replace '\\+', '\'
  while ($p.StartsWith(".\")) { $p = $p.Substring(2) }
  return $p.Trim()
}

function Normalize-Key([string]$Path) {
  return (Normalize-AssetPath $Path).ToLowerInvariant()
}

function Get-RelativePath([string]$Base, [string]$Path) {
  $baseUri = [Uri](([IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'))
  $pathUri = [Uri]([IO.Path]::GetFullPath($Path))
  return [Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace('/', '\')
}

function Get-RelativePathForMap([string]$FromFile, [string]$ToFile) {
  $fromDir = Split-Path -Parent ([IO.Path]::GetFullPath($FromFile))
  return (Get-RelativePath $fromDir ([IO.Path]::GetFullPath($ToFile))).Replace('\', '/')
}

function Get-Ext([string]$Path) {
  return ([IO.Path]::GetExtension($Path)).ToLowerInvariant()
}

function Get-LikelyAssetType([string]$Reference) {
  $ext = Get-Ext $Reference
  if ($ext -eq ".tsx") { return "tileset" }
  if ($imageExts -contains $ext) { return "tilesheet" }
  if ($ext -eq ".tmx" -or $ext -eq ".tmj") { return "map" }
  if ($ext -eq ".json") { return "map_config" }
  return "unknown"
}

function Add-Lookup($Table, [string]$Key, $Value) {
  if ([string]::IsNullOrWhiteSpace($Key)) { return }
  if (-not $Table.ContainsKey($Key)) {
    $Table[$Key] = New-Object System.Collections.Generic.List[object]
  }
  $Table[$Key].Add($Value)
}

function Get-ModAnchorRelative([object]$Entry) {
  $copied = [IO.Path]::GetFullPath([string]$Entry.copiedPath)
  $catRoot = Join-Path $MissionRoot ([string]$Entry.sourceCategory)
  if ($Entry.sourceCategory -eq "moonvillage") {
    $rel = Get-RelativePath $catRoot $copied
    $parts = $rel -split '\\'
    if ($parts.Count -ge 3) { return ($parts[2..($parts.Count - 1)] -join '\') }
    return $rel
  }
  $modRoot = Join-Path $catRoot ([string]$Entry.sourceMod)
  if (Test-Path -LiteralPath $modRoot) {
    return Get-RelativePath $modRoot $copied
  }
  return Get-RelativePath $catRoot $copied
}

function Get-RepairPath([object]$Entry) {
  $copied = [IO.Path]::GetFullPath([string]$Entry.copiedPath)
  $rel = Get-RelativePath $MissionRoot $copied
  return Join-Path $RepairedRoot $rel
}

function Test-VanillaReference([string]$Reference) {
  $n = (Normalize-Key $Reference)
  $leaf = [IO.Path]::GetFileName($n)
  $vanillaLeaves = @(
    "paths.png", "springobjects.png", "towninterior.png", "towninterior_2.png",
    "walls_and_floors.png", "cave.png", "mine.png", "mine_dark.png",
    "mine_dangerous.png", "volcano_dungeon.png", "volcano_caldera.png",
    "island_tilesheet_1.png", "outdoors.png", "outdoors2.png", "untitled tile sheet.png",
    "deserttiles.png", "festivals.png", "bathhouse_tiles.png", "sewer_tilesheet.png",
    "cooptiles.png", "barn_tiles.png", "farmhouse_tiles.png", "beach_tilesheet.png"
  )
  if ($vanillaLeaves -contains $leaf) { return $true }
  if ($n -match '^(mines|maps|terrainfeatures|looseSprites|buildings)\\') { return $true }
  if ($n -match '^(mines|maps)/') { return $true }
  return $false
}

function Get-CommonRootScore([string]$A, [string]$B) {
  $aParts = (Normalize-Key $A) -split '\\'
  $bParts = (Normalize-Key $B) -split '\\'
  $score = 0
  $max = [Math]::Min($aParts.Count, $bParts.Count)
  for ($i = 0; $i -lt $max; $i++) {
    if ($aParts[$i] -ne $bParts[$i]) { break }
    $score++
  }
  return $score
}

function Get-Candidates([object]$Missing, [hashtable]$Lookups, [hashtable]$OriginalToEntry) {
  $reference = [string]$Missing.reference
  $refKey = Normalize-Key $reference
  $leafKey = ([IO.Path]::GetFileName($reference)).ToLowerInvariant()
  $refType = Get-LikelyAssetType $reference
  $candidates = New-Object System.Collections.Generic.List[object]

  foreach ($tableName in @("exactPath", "normalizedPath", "fileNameLower")) {
    $table = $Lookups[$tableName]
    $keys = @()
    if ($tableName -eq "fileNameLower") { $keys = @($leafKey) } else { $keys = @($refKey) }
    foreach ($key in $keys) {
      if ($table.ContainsKey($key)) {
        foreach ($entry in $table[$key]) {
          if ($refType -ne "unknown" -and $entry.fileType -ne $refType) { continue }
          $candidates.Add([pscustomobject]@{
            entry = $entry
            matchKind = $tableName
            score = 0
          })
        }
      }
    }
  }

  $unique = @{}
  foreach ($candidate in $candidates) {
    $entry = $candidate.entry
    $key = ([string]$entry.copiedPath).ToLowerInvariant()
    if (-not $unique.ContainsKey($key)) {
      $sameMod = ($entry.sourceCategory -eq $Missing.sourceCategory -and $entry.sourceMod -eq $Missing.sourceMod)
      $sameCategory = ($entry.sourceCategory -eq $Missing.sourceCategory)
      $refDir = Split-Path -Parent (Normalize-Key $reference)
      $entryRel = Normalize-Key $entry.normalizedRelativePath
      $folderScore = if ($refDir) { Get-CommonRootScore $refDir $entryRel } else { 0 }
      $score = 0
      if ($candidate.matchKind -eq "exactPath" -or $candidate.matchKind -eq "normalizedPath") { $score += 40 }
      if ($candidate.matchKind -eq "fileNameLower") { $score += 10 }
      if ($sameMod) { $score += 50 } elseif ($sameCategory) { $score += 15 }
      $score += [Math]::Min($folderScore, 8)
      $unique[$key] = [pscustomobject]@{
        entry = $entry
        matchKind = $candidate.matchKind
        score = $score
        sameMod = $sameMod
        sameCategory = $sameCategory
        folderScore = $folderScore
      }
    }
  }
  return @($unique.Values | Sort-Object score -Descending)
}

function Classify-MissingReference([object]$Missing, [array]$Candidates) {
  $reference = [string]$Missing.reference
  $refType = Get-LikelyAssetType $reference
  $sameMod = @($Candidates | Where-Object { $_.sameMod })
  $sameCategory = @($Candidates | Where-Object { $_.sameCategory })
  $allCount = @($Candidates).Count
  $sameModStrong = @($sameMod | Where-Object { $_.score -ge 60 })

  if ($sameModStrong.Count -eq 1) {
    return [pscustomobject]@{
      classification = "resolved_local_copy"
      candidate = $sameModStrong[0]
      confidence = 0.95
      reason = "One strong same-source-mod $refType match exists in mission_assets."
      shouldAutoRepair = $true
    }
  }
  if ($sameMod.Count -eq 1 -and $sameMod[0].score -ge 55) {
    return [pscustomobject]@{
      classification = "resolved_local_copy"
      candidate = $sameMod[0]
      confidence = 0.88
      reason = "One same-source-mod candidate matches the missing file name and type."
      shouldAutoRepair = $true
    }
  }
  if ($sameMod.Count -gt 1) {
    return [pscustomobject]@{
      classification = "likely_path_error"
      candidate = $sameMod[0]
      confidence = 0.55
      reason = "Multiple same-source-mod candidates match; path likely needs human disambiguation."
      shouldAutoRepair = $false
    }
  }
  if (Test-VanillaReference $reference) {
    return [pscustomobject]@{
      classification = "external_vanilla_asset"
      candidate = $null
      confidence = 0.9
      reason = "Reference name/path matches common Stardew Valley vanilla tilesheet assets."
      shouldAutoRepair = $false
    }
  }
  if ($sameCategory.Count -eq 1) {
    return [pscustomobject]@{
      classification = "external_mod_asset"
      candidate = $sameCategory[0]
      confidence = 0.72
      reason = "One matching asset exists, but it belongs to a different source mod in the same source category."
      shouldAutoRepair = $false
    }
  }
  if ($allCount -eq 1) {
    return [pscustomobject]@{
      classification = "external_mod_asset"
      candidate = $Candidates[0]
      confidence = 0.65
      reason = "One matching asset exists in another collected source, so this likely depends on another mod asset."
      shouldAutoRepair = $false
    }
  }
  if ($allCount -gt 1) {
    return [pscustomobject]@{
      classification = "likely_path_error"
      candidate = $Candidates[0]
      confidence = 0.45
      reason = "The file name exists in collected assets but has multiple possible matches."
      shouldAutoRepair = $false
    }
  }
  if ((Get-Ext $reference) -eq "") {
    return [pscustomobject]@{
      classification = "uncertain"
      candidate = $null
      confidence = 0.2
      reason = "Reference has no extension and no collected match."
      shouldAutoRepair = $false
    }
  }
  return [pscustomobject]@{
    classification = "true_missing"
    candidate = $null
    confidence = 0.62
    reason = "No matching collected asset and not recognized as a vanilla tilesheet reference."
    shouldAutoRepair = $false
  }
}

function Update-ReferenceInText([string]$Text, [string]$OldRef, [string]$NewRef, [string]$Extension) {
  if ($Extension -eq ".tmx" -or $Extension -eq ".tsx") {
    $escaped = [System.Security.SecurityElement]::Escape($OldRef)
    $newEscaped = [System.Security.SecurityElement]::Escape($NewRef)
    $text2 = $Text.Replace("source=`"$escaped`"", "source=`"$newEscaped`"")
    if ($OldRef -ne $escaped) {
      $text2 = $text2.Replace("source=`"$OldRef`"", "source=`"$newEscaped`"")
    }
    return $text2
  }
  if ($Extension -eq ".tmj" -or $Extension -eq ".json") {
    return $Text.Replace("`"$OldRef`"", "`"$NewRef`"")
  }
  return $Text
}

function Validate-TiledFile([string]$Path) {
  $ext = (Get-Ext $Path)
  $issues = New-Object System.Collections.Generic.List[object]
  try {
    if ($ext -eq ".tmx" -or $ext -eq ".tsx") {
      [xml]$xml = Get-Content -LiteralPath $Path -Raw
      $nodes = $xml.SelectNodes("//*[@source]")
      foreach ($node in $nodes) {
        $src = [string]$node.source
        if ($src -match '(?i)\.(png|ase|aseprite|bmp|jpe?g|tsx)$') {
          $candidate = Join-Path (Split-Path -Parent $Path) ($src -replace '/', '\')
          if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            if (-not (Test-VanillaReference $src)) {
              $issues.Add([pscustomobject]@{ file = $Path; reference = $src; issue = "Referenced local asset does not resolve from repaired file." })
            }
          }
        }
      }
    } elseif ($ext -eq ".tmj") {
      $json = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
      foreach ($ts in @($json.tilesets)) {
        foreach ($prop in @("source", "image")) {
          if ($ts.PSObject.Properties.Name -contains $prop) {
            $src = [string]$ts.$prop
            $candidate = Join-Path (Split-Path -Parent $Path) ($src -replace '/', '\')
            if ($src -and -not (Test-Path -LiteralPath $candidate -PathType Leaf) -and -not (Test-VanillaReference $src)) {
              $issues.Add([pscustomobject]@{ file = $Path; reference = $src; issue = "Referenced local asset does not resolve from repaired file." })
            }
          }
        }
      }
    }
  } catch {
    $issues.Add([pscustomobject]@{ file = $Path; reference = ""; issue = "Parse failure: $($_.Exception.Message)" })
  }
  return @($issues)
}

if (-not (Test-Path -LiteralPath $InventoryPath -PathType Leaf)) {
  throw "Missing inventory: $InventoryPath"
}
if (-not (Test-Path -LiteralPath $MissingReportPath -PathType Leaf)) {
  throw "Missing report: $MissingReportPath"
}

Ensure-Directory $DatabaseRoot
Ensure-Directory $ReportsRoot
New-CleanDirectory $RepairedRoot
foreach ($category in @("moonvillage", "reference_mods", "stardew_mods")) {
  Ensure-Directory (Join-Path $RepairedRoot $category)
}

$inventoryDoc = Get-Content -LiteralPath $InventoryPath -Raw | ConvertFrom-Json
$missingReportText = Get-Content -LiteralPath $MissingReportPath -Raw
$files = @($inventoryDoc.files)
$missingRefs = @($inventoryDoc.missingReferences)

$originalToEntry = @{}
$copiedToEntry = @{}
$indexEntries = New-Object System.Collections.Generic.List[object]
$lookups = @{
  exactPath = @{}
  normalizedPath = @{}
  fileName = @{}
  fileNameLower = @{}
  caseInsensitivePath = @{}
  slashNormalized = @{}
  sameSourceMod = @{}
  sameFolderTree = @{}
}

foreach ($file in $files) {
  $rel = Get-ModAnchorRelative $file
  $normRel = Normalize-AssetPath $rel
  $entry = [pscustomobject]@{
    fileName = [string]$file.fileName
    normalizedRelativePath = $normRel
    copiedPath = [string]$file.copiedPath
    originalPath = [string]$file.originalPath
    sourceCategory = [string]$file.sourceCategory
    sourceMod = [string]$file.sourceMod
    extension = [string]$file.extension
    fileType = [string]$file.fileType
  }
  $indexEntries.Add($entry)
  $originalToEntry[$entry.originalPath.ToLowerInvariant()] = $entry
  $copiedToEntry[$entry.copiedPath.ToLowerInvariant()] = $entry
  Add-Lookup $lookups.exactPath $entry.normalizedRelativePath $entry
  Add-Lookup $lookups.normalizedPath (Normalize-Key $entry.normalizedRelativePath) $entry
  Add-Lookup $lookups.fileName $entry.fileName $entry
  Add-Lookup $lookups.fileNameLower $entry.fileName.ToLowerInvariant() $entry
  Add-Lookup $lookups.caseInsensitivePath (Normalize-Key $entry.normalizedRelativePath) $entry
  Add-Lookup $lookups.slashNormalized (($entry.normalizedRelativePath -replace '\\', '/').ToLowerInvariant()) $entry
  Add-Lookup $lookups.sameSourceMod (($entry.sourceCategory + "|" + $entry.sourceMod).ToLowerInvariant()) $entry
  $folderKey = (Split-Path -Parent $entry.normalizedRelativePath)
  Add-Lookup $lookups.sameFolderTree (($entry.sourceCategory + "|" + $entry.sourceMod + "|" + $folderKey).ToLowerInvariant()) $entry
}

$serializableLookups = @{}
foreach ($name in $lookups.Keys) {
  $serializableLookups[$name] = @{}
  foreach ($key in $lookups[$name].Keys) {
    $serializableLookups[$name][$key] = @($lookups[$name][$key] | ForEach-Object { $_.copiedPath })
  }
}

$assetReferenceIndex = [pscustomobject]@{
  generatedAt = (Get-Date).ToString("o")
  missionRoot = $MissionRoot
  sourceInventory = $InventoryPath
  files = @($indexEntries.ToArray())
  lookups = $serializableLookups
}
$assetReferenceIndex | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $DatabaseRoot "asset_reference_index.json") -Encoding UTF8

$repairPlan = New-Object System.Collections.Generic.List[object]
$groupedMissing = New-Object System.Collections.Generic.List[object]

foreach ($miss in $missingRefs) {
  $candidates = @(Get-Candidates $miss $lookups $originalToEntry)
  $classification = Classify-MissingReference $miss $candidates
  $candidateEntry = if ($classification.candidate) { $classification.candidate.entry } else { $null }
  $referringEntry = $null
  $refKey = ([string]$miss.referringFile).ToLowerInvariant()
  if ($originalToEntry.ContainsKey($refKey)) { $referringEntry = $originalToEntry[$refKey] }
  $suggested = $null
  if ($candidateEntry -and $referringEntry) {
    $repairDest = Get-RepairPath $referringEntry
    $suggested = Get-RelativePathForMap $repairDest $candidateEntry.copiedPath
  }
  $planEntry = [pscustomobject]@{
    sourceCategory = [string]$miss.sourceCategory
    sourceMod = [string]$miss.sourceMod
    referencingFile = [string]$miss.referringFile
    referencingCopiedPath = if ($referringEntry) { $referringEntry.copiedPath } else { $null }
    missingReference = [string]$miss.reference
    extension = Get-Ext ([string]$miss.reference)
    likelyAssetType = Get-LikelyAssetType ([string]$miss.reference)
    classification = $classification.classification
    suggestedReplacementPath = $suggested
    confidence = $classification.confidence
    reason = $classification.reason
    shouldAutoRepair = [bool]$classification.shouldAutoRepair
    candidateCopiedPath = if ($candidateEntry) { $candidateEntry.copiedPath } else { $null }
    candidateOriginalPath = if ($candidateEntry) { $candidateEntry.originalPath } else { $null }
    candidateCount = $candidates.Count
  }
  $repairPlan.Add($planEntry)
}

$repairPlanDoc = [pscustomobject]@{
  generatedAt = (Get-Date).ToString("o")
  sourceInventory = $InventoryPath
  sourceMissingReport = $MissingReportPath
  entries = @($repairPlan.ToArray())
}
$repairPlanDoc | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $ReportsRoot "reference_repair_plan.json") -Encoding UTF8

$changes = New-Object System.Collections.Generic.List[object]
$validationIssues = New-Object System.Collections.Generic.List[object]
$repairsByFile = @{}
foreach ($entry in @($repairPlan | Where-Object { $_.shouldAutoRepair -eq $true -and $_.referencingCopiedPath })) {
  $key = ([string]$entry.referencingCopiedPath).ToLowerInvariant()
  if (-not $repairsByFile.ContainsKey($key)) {
    $repairsByFile[$key] = New-Object System.Collections.Generic.List[object]
  }
  $repairsByFile[$key].Add($entry)
}

foreach ($key in $repairsByFile.Keys) {
  $refEntry = $copiedToEntry[$key]
  $sourcePath = [string]$refEntry.copiedPath
  $destPath = Get-RepairPath $refEntry
  Ensure-Directory (Split-Path -Parent $destPath)
  Copy-Item -LiteralPath $sourcePath -Destination $destPath -Force
  $text = Get-Content -LiteralPath $destPath -Raw
  $ext = Get-Ext $destPath
  foreach ($repair in $repairsByFile[$key]) {
    $old = [string]$repair.missingReference
    $new = [string]$repair.suggestedReplacementPath
    $updated = Update-ReferenceInText $text $old $new $ext
    if ($updated -ne $text) {
      $text = $updated
      $changes.Add([pscustomobject]@{
        fileRepaired = $destPath
        sourceCopiedFile = $sourcePath
        oldReference = $old
        newReference = $new
        confidence = $repair.confidence
        reason = $repair.reason
      })
    } else {
      $validationIssues.Add([pscustomobject]@{
        file = $destPath
        reference = $old
        issue = "Auto-repair was planned but the exact reference string was not found in the copied file."
      })
    }
  }
  Set-Content -LiteralPath $destPath -Value $text -Encoding UTF8
  foreach ($issue in (Validate-TiledFile $destPath)) { $validationIssues.Add($issue) }
}

$changesDoc = [pscustomobject]@{
  generatedAt = (Get-Date).ToString("o")
  changes = @($changes.ToArray())
  validationIssues = @($validationIssues.ToArray())
}
$changesDoc | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $ReportsRoot "reference_changes.json") -Encoding UTF8

$planMd = New-Object System.Collections.Generic.List[string]
$planMd.Add("# Reference Repair Plan")
$planMd.Add("")
$planMd.Add("- Generated: $(Get-Date -Format s)")
$planMd.Add("- Missing references reviewed: $($repairPlan.Count)")
$planMd.Add("- Auto-repair entries: $(@($repairPlan | Where-Object shouldAutoRepair).Count)")
$planMd.Add("")
$planMd.Add("## Classification Counts")
foreach ($group in ($repairPlan | Group-Object classification | Sort-Object Name)) {
  $planMd.Add("- $($group.Name): $($group.Count)")
}
$planMd.Add("")
$planMd.Add("## Auto-Repair Entries")
foreach ($entry in ($repairPlan | Where-Object shouldAutoRepair | Sort-Object sourceCategory, sourceMod, referencingFile, missingReference)) {
  $planMd.Add("- $($entry.sourceCategory) / $($entry.sourceMod): $($entry.referencingFile)")
  $planMd.Add("  - $($entry.missingReference) -> $($entry.suggestedReplacementPath) ($($entry.confidence))")
}
$planMd | Set-Content -LiteralPath (Join-Path $ReportsRoot "reference_repair_plan.md") -Encoding UTF8

$summary = New-Object System.Collections.Generic.List[string]
$summary.Add("# Reference Audit Summary")
$summary.Add("")
$summary.Add("- Generated: $(Get-Date -Format s)")
$summary.Add("- Total missing references reviewed: $($repairPlan.Count)")
foreach ($name in @("resolved_local_copy", "external_vanilla_asset", "external_mod_asset", "likely_path_error", "true_missing", "uncertain")) {
  $summary.Add("- $($name): $(@($repairPlan | Where-Object classification -eq $name).Count)")
}
$summary.Add("- Repaired map/tileset/config files: $($repairsByFile.Keys.Count)")
$summary.Add("- Reference changes written: $($changes.Count)")
$summary.Add("- Validation issues after repair: $($validationIssues.Count)")
$summary.Add("")
$summary.Add("## Most Common Missing Reference Patterns")
foreach ($group in ($repairPlan | Group-Object missingReference | Sort-Object Count -Descending | Select-Object -First 25)) {
  $summary.Add("- $($group.Name): $($group.Count)")
}
$summary.Add("")
$summary.Add("## Recommended Next Action")
if ($validationIssues.Count -gt 0) {
  $summary.Add("Review validation issues in reference_changes.json before using repaired files.")
} elseif ($changes.Count -gt 0) {
  $summary.Add("Review repaired_assets and unresolved_references.md, then decide whether external vanilla references should remain external or be supplied from an unpacked Stardew Valley content source.")
} else {
  $summary.Add("No safe automatic repairs were identified; review unresolved_references.md for human decisions.")
}
$summary | Set-Content -LiteralPath (Join-Path $ReportsRoot "reference_audit_summary.md") -Encoding UTF8

$unresolved = New-Object System.Collections.Generic.List[string]
$unresolved.Add("# Unresolved References")
$unresolved.Add("")
$unresolved.Add("These entries were not repaired automatically.")
$unresolved.Add("")
foreach ($entry in ($repairPlan | Where-Object { -not $_.shouldAutoRepair } | Sort-Object classification, sourceCategory, sourceMod, missingReference)) {
  $human = switch ($entry.classification) {
    "external_vanilla_asset" { "Decide whether to keep this as a vanilla external dependency or provide unpacked vanilla tilesheets for offline analysis." }
    "external_mod_asset" { "Confirm dependency source and whether cross-mod references should be linked or copied into a shared dependency set." }
    "likely_path_error" { "Choose the intended target among multiple matching collected assets." }
    "true_missing" { "Locate or recreate the missing asset, or mark the map as requiring an external dependency." }
    default { "Inspect manually; confidence is too low for an automatic edit." }
  }
  $unresolved.Add("- $($entry.classification) / $($entry.sourceCategory) / $($entry.sourceMod): $($entry.referencingFile)")
  $unresolved.Add("  - Missing: $($entry.missingReference)")
  $unresolved.Add("  - Reason: $($entry.reason)")
  $unresolved.Add("  - Human decision needed: $human")
}
$unresolved | Set-Content -LiteralPath (Join-Path $ReportsRoot "unresolved_references.md") -Encoding UTF8

Write-Output "Reviewed $($repairPlan.Count) missing references."
Write-Output "Auto-repaired $($changes.Count) references across $($repairsByFile.Keys.Count) files."
Write-Output "Validation issues: $($validationIssues.Count)"
