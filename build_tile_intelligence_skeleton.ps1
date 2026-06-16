Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ToolRoot = $PSScriptRoot
$MissionRoot = Join-Path $ToolRoot "mission_assets"
$DatabaseRoot = Join-Path $ToolRoot "database"
$ReportsRoot = Join-Path $ToolRoot "reports"
$PreviewsRoot = Join-Path $ToolRoot "previews"
$WorkingRoot = Join-Path $ToolRoot "working"
$TilesheetPreviewRoot = Join-Path $PreviewsRoot "tilesheets"

$InventoryPath = Join-Path $MissionRoot "reports\asset_inventory.json"
$ReferenceIndexPath = Join-Path $DatabaseRoot "asset_reference_index.json"
$RepairPlanPath = Join-Path $ReportsRoot "reference_repair_plan.json"
$AuditSummaryPath = Join-Path $ReportsRoot "reference_audit_summary.md"
$UnresolvedPath = Join-Path $ReportsRoot "unresolved_references.md"

$imageExts = @(".png", ".ase", ".aseprite", ".bmp", ".jpg", ".jpeg")
$gidFlipMask = 0x1FFFFFFF

function Ensure-Directory([string]$Path) {
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

function Get-SafeFileName([string]$Name) {
  $safe = $Name -replace '[<>:"/\\|?*]', '_'
  if ($safe.Length -gt 130) { $safe = $safe.Substring(0, 130) }
  return $safe
}

function Get-ShortHash([string]$Value) {
  $sha1 = [System.Security.Cryptography.SHA1]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $hash = $sha1.ComputeHash($bytes)
    return -join ($hash[0..5] | ForEach-Object { $_.ToString("x2") })
  } finally {
    $sha1.Dispose()
  }
}

function Add-ListValue($Table, [string]$Key, $Value) {
  if (-not $Table.ContainsKey($Key)) {
    $Table[$Key] = New-Object System.Collections.Generic.List[object]
  }
  $Table[$Key].Add($Value)
}

function Add-Count($Table, [string]$Key, [int]$Amount = 1) {
  if ([string]::IsNullOrWhiteSpace($Key)) { return }
  if (-not $Table.ContainsKey($Key)) { $Table[$Key] = 0 }
  $Table[$Key] += $Amount
}

function Get-PropertyMapFromXml($Node) {
  $props = @{}
  if ($null -eq $Node) { return $props }
  $propertyNodes = $Node.SelectNodes("properties/property")
  foreach ($p in $propertyNodes) {
    $name = Get-XmlAttr $p "name"
    if (-not $name) { continue }
    $value = if (Get-XmlAttr $p "value") { Get-XmlAttr $p "value" } else { [string]$p.InnerText }
    $props[$name] = $value
  }
  return $props
}

function Get-XmlAttr($Node, [string]$Name) {
  if ($null -eq $Node -or -not $Node.HasAttribute($Name)) { return $null }
  return [string]$Node.GetAttribute($Name)
}

function Test-WarpProperty($Properties) {
  foreach ($k in $Properties.Keys) {
    if ($k -match '(?i)warp|door|destination|exit|location') { return $true }
    if ([string]$Properties[$k] -match '(?i)warp|door|destination|exit|location') { return $true }
  }
  return $false
}

function Decode-TmxData($DataNode) {
  $encoding = Get-XmlAttr $DataNode "encoding"
  $compression = Get-XmlAttr $DataNode "compression"
  $text = ([string]$DataNode.InnerText).Trim()
  if ([string]::IsNullOrWhiteSpace($text)) { return @() }
  if ($encoding -eq "csv") {
    return @($text -split '[,\s]+' | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [uint32]$_ })
  }
  if ($encoding -eq "base64") {
    $bytes = [Convert]::FromBase64String(($text -replace '\s+', ''))
    if ($compression -eq "zlib") {
      $payload = $bytes
      if (-not ("System.IO.Compression.ZLibStream" -as [type]) -and $bytes.Length -gt 6) {
        $payload = New-Object byte[] ($bytes.Length - 6)
        [Array]::Copy($bytes, 2, $payload, 0, $payload.Length)
      }
      $input = [IO.MemoryStream]::new($payload)
      $output = [IO.MemoryStream]::new()
      try {
        if ("System.IO.Compression.ZLibStream" -as [type]) {
          $z = [IO.Compression.ZLibStream]::new($input, [IO.Compression.CompressionMode]::Decompress)
          try { $z.CopyTo($output) } finally { $z.Dispose() }
        } else {
          $z = [IO.Compression.DeflateStream]::new($input, [IO.Compression.CompressionMode]::Decompress)
          try { $z.CopyTo($output) } finally { $z.Dispose() }
        }
        $bytes = $output.ToArray()
      } finally {
        $input.Dispose()
        $output.Dispose()
      }
    } elseif ($compression -eq "gzip") {
      $input = [IO.MemoryStream]::new($bytes)
      $output = [IO.MemoryStream]::new()
      try {
        $gz = [IO.Compression.GZipStream]::new($input, [IO.Compression.CompressionMode]::Decompress)
        try { $gz.CopyTo($output) } finally { $gz.Dispose() }
        $bytes = $output.ToArray()
      } finally {
        $input.Dispose()
        $output.Dispose()
      }
    } elseif ($compression) {
      throw "Unsupported TMX compression '$compression'"
    }
    $gids = New-Object System.Collections.Generic.List[uint32]
    for ($i = 0; $i -le $bytes.Length - 4; $i += 4) {
      $gids.Add([BitConverter]::ToUInt32($bytes, $i))
    }
    return @($gids)
  }
  throw "Unsupported TMX data encoding '$encoding'"
}

function Get-ImageDimensions([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
  try {
    Add-Type -AssemblyName System.Drawing -ErrorAction SilentlyContinue
    $img = [System.Drawing.Image]::FromFile($Path)
    try {
      return [pscustomobject]@{ width = $img.Width; height = $img.Height }
    } finally {
      $img.Dispose()
    }
  } catch {
    return $null
  }
}

function Resolve-ImageEntry([string]$Reference, [object]$MapEntry, [hashtable]$Lookups) {
  $leaf = [IO.Path]::GetFileName($Reference).ToLowerInvariant()
  if (-not $leaf -or -not $Lookups.byFileName.ContainsKey($leaf)) { return $null }
  $candidates = @($Lookups.byFileName[$leaf] | Where-Object {
    $_.fileType -eq "tilesheet" -and $_.sourceCategory -eq $MapEntry.sourceCategory -and $_.sourceMod -eq $MapEntry.sourceMod
  })
  if ($candidates.Count -eq 1) { return $candidates[0] }
  if ($candidates.Count -gt 1) {
    $refKey = Normalize-Key $Reference
    $exact = @($candidates | Where-Object { (Normalize-Key $_.normalizedRelativePath).EndsWith($refKey) })
    if ($exact.Count -eq 1) { return $exact[0] }
    return $candidates[0]
  }
  $cross = @($Lookups.byFileName[$leaf] | Where-Object { $_.fileType -eq "tilesheet" })
  if ($cross.Count -eq 1) { return $cross[0] }
  return $null
}

function Get-EvidenceLabel($LayerCounts) {
  $total = 0
  foreach ($v in $LayerCounts.Values) { $total += [int]$v }
  if ($total -eq 0) {
    return [pscustomobject]@{ label = "unknown"; confidence = 0.0; reason = "No non-empty layer observations." }
  }
  $groups = @{
    likely_ground_or_floor = @("back", "paths", "path", "floor", "ground")
    likely_wall_or_blocker = @("buildings", "building", "walls", "wall", "collision", "back-buildings")
    likely_front_decoration = @("front", "alwaysfront", "always front", "foreground")
    likely_object_or_furniture = @("furniture", "objects", "object", "decor", "interior")
    likely_transition_candidate = @("paths", "path", "water", "bridge", "edge", "transition")
  }
  $bestLabel = "unknown"
  $bestCount = 0
  $bestReason = "Layer usage is mixed or does not match known Stardew layer naming conventions."
  foreach ($label in $groups.Keys) {
    $count = 0
    foreach ($layer in $LayerCounts.Keys) {
      $l = $layer.ToLowerInvariant()
      foreach ($word in $groups[$label]) {
        if ($l -eq $word -or $l -like "*$word*") {
          $count += [int]$LayerCounts[$layer]
          break
        }
      }
    }
    if ($count -gt $bestCount) {
      $bestCount = $count
      $bestLabel = $label
      $bestReason = "Most observations are on layer names associated with $label."
    }
  }
  if ($bestCount -eq 0) {
    return [pscustomobject]@{ label = "unknown"; confidence = 0.2; reason = $bestReason }
  }
  $ratio = $bestCount / [double]$total
  $confidence = [Math]::Round([Math]::Min(0.85, 0.35 + ($ratio * 0.45)), 3)
  return [pscustomobject]@{ label = $bestLabel; confidence = $confidence; reason = $bestReason }
}

function Get-DependencyStatus([string]$OriginalPath, [hashtable]$PlanByFile) {
  $key = $OriginalPath.ToLowerInvariant()
  if (-not $PlanByFile.ContainsKey($key)) { return "fully_local" }
  $classes = @($PlanByFile[$key] | ForEach-Object { $_.classification })
  if ($classes -contains "true_missing") { return "has_true_missing_refs" }
  if ($classes -contains "likely_path_error") { return "ambiguous_refs" }
  if ($classes -contains "external_mod_asset") { return "needs_external_mod_assets" }
  if ($classes -contains "external_vanilla_asset") { return "needs_vanilla_assets" }
  return "fully_local"
}

function Get-LearningPriority([object]$MapEntry, [string]$DependencyStatus, [int]$TrueMissingCount, [int]$AmbiguousCount) {
  if ($MapEntry.parseStatus -eq "failed") { return "exclude" }
  if ($TrueMissingCount -gt 5) { return "exclude" }
  if ($DependencyStatus -eq "has_true_missing_refs") { return "exclude" }
  if ($MapEntry.sourceCategory -eq "moonvillage" -and ($DependencyStatus -eq "fully_local" -or $DependencyStatus -eq "needs_vanilla_assets")) { return "high" }
  if ($DependencyStatus -eq "fully_local") { return "high" }
  if ($DependencyStatus -eq "needs_vanilla_assets") { return "medium" }
  if ($DependencyStatus -eq "ambiguous_refs" -or $AmbiguousCount -gt 0) { return "low" }
  return "low"
}

function New-MapId([object]$Entry) {
  return (Get-ShortHash ([string]$Entry.copiedPath)) + "_" + ([IO.Path]::GetFileNameWithoutExtension([string]$Entry.fileName))
}

function Resolve-GidTileset([uint32]$Gid, [array]$Tilesets) {
  if ($Gid -eq 0) { return $null }
  $clean = [uint32]($Gid -band $gidFlipMask)
  $match = $null
  foreach ($ts in $Tilesets) {
    if ([uint32]$ts.firstgid -le $clean) { $match = $ts } else { break }
  }
  if (-not $match) { return $null }
  return [pscustomobject]@{ tileset = $match; localTileId = [int]($clean - [uint32]$match.firstgid); cleanGid = $clean }
}

function Add-TileObservation([hashtable]$TileUsage, [string]$TileKey, [object]$Obs) {
  if (-not $TileUsage.ContainsKey($TileKey)) {
    $TileUsage[$TileKey] = [pscustomobject]@{
      tileKey = $TileKey
      sourceCategory = $Obs.sourceCategory
      sourceMod = $Obs.sourceMod
      tilesetName = $Obs.tilesetName
      imageName = $Obs.imageName
      localTileId = $Obs.localTileId
      globalTileIdsUsed = @{}
      copiedImagePath = $Obs.copiedImagePath
      sourceMapsUsedBy = @{}
      observedLayers = @{}
      observedCount = 0
      coordinateExamples = New-Object System.Collections.Generic.List[object]
      nearEdgeCount = 0
      nearWarpLayerCount = 0
      neighborCounts = @{}
      existingProperties = $Obs.existingProperties
      existingTerrainData = $Obs.existingTerrainData
      existingWangData = $Obs.existingWangData
    }
  }
  $entry = $TileUsage[$TileKey]
  $entry.observedCount++
  Add-Count $entry.globalTileIdsUsed ([string]$Obs.globalTileId)
  Add-Count $entry.sourceMapsUsedBy $Obs.mapId
  Add-Count $entry.observedLayers $Obs.layerName
  if ($entry.coordinateExamples.Count -lt 12) {
    $entry.coordinateExamples.Add([pscustomobject]@{ mapId = $Obs.mapId; layer = $Obs.layerName; x = $Obs.x; y = $Obs.y })
  }
  if ($Obs.nearEdge) { $entry.nearEdgeCount++ }
  if ($Obs.nearWarpLayer) { $entry.nearWarpLayerCount++ }
}

function Add-NeighborEvidence([hashtable]$TileUsage, [object[]]$CellKeys, [int]$Width, [int]$Height) {
  for ($i = 0; $i -lt $CellKeys.Count; $i++) {
    $tileKey = [string]$CellKeys[$i]
    if ([string]::IsNullOrWhiteSpace($tileKey) -or -not $TileUsage.ContainsKey($tileKey)) { continue }
    $x = $i % $Width
    $y = [Math]::Floor($i / $Width)
    $neighbors = @(
      @($x - 1, $y),
      @($x + 1, $y),
      @($x, $y - 1),
      @($x, $y + 1)
    )
    foreach ($n in $neighbors) {
      $nx = [int]$n[0]; $ny = [int]$n[1]
      if ($nx -lt 0 -or $ny -lt 0 -or $nx -ge $Width -or $ny -ge $Height) { continue }
      $neighborKey = [string]$CellKeys[($ny * $Width) + $nx]
      if ([string]::IsNullOrWhiteSpace($neighborKey)) { continue }
      Add-Count $TileUsage[$tileKey].neighborCounts $neighborKey
    }
  }
}

function Generate-Preview([object]$ImageEntry, [string]$OutputRoot, [int]$TileWidth = 16, [int]$TileHeight = 16) {
  if (-not (Test-Path -LiteralPath $ImageEntry.copiedPath -PathType Leaf)) { return $null }
  try {
    Add-Type -AssemblyName System.Drawing -ErrorAction SilentlyContinue
    $src = [System.Drawing.Bitmap]::FromFile([string]$ImageEntry.copiedPath)
    try {
      if ($src.Width -lt $TileWidth -or $src.Height -lt $TileHeight) { return $null }
      $scale = if ($src.Width -lt 512) { 2 } else { 1 }
      $outW = $src.Width * $scale
      $outH = $src.Height * $scale
      $bmp = [System.Drawing.Bitmap]::new($outW, $outH)
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      try {
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
        $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
        $g.DrawImage($src, 0, 0, $outW, $outH)
        $pen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(150, 255, 255, 255), 1)
        $brushBg = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(170, 0, 0, 0))
        $brushText = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
        $font = [System.Drawing.Font]::new("Arial", [Math]::Max(6, 7 * $scale), [System.Drawing.FontStyle]::Regular)
        try {
          $cols = [Math]::Floor($src.Width / $TileWidth)
          $rows = [Math]::Floor($src.Height / $TileHeight)
          for ($y = 0; $y -le $rows; $y++) { $g.DrawLine($pen, 0, $y * $TileHeight * $scale, $outW, $y * $TileHeight * $scale) }
          for ($x = 0; $x -le $cols; $x++) { $g.DrawLine($pen, $x * $TileWidth * $scale, 0, $x * $TileWidth * $scale, $outH) }
          for ($row = 0; $row -lt $rows; $row++) {
            for ($col = 0; $col -lt $cols; $col++) {
              $id = $row * $cols + $col
              $tx = $col * $TileWidth * $scale
              $ty = $row * $TileHeight * $scale
              $text = [string]$id
              $size = $g.MeasureString($text, $font)
              $g.FillRectangle($brushBg, $tx, $ty, [Math]::Min($size.Width + 2, $TileWidth * $scale), [Math]::Min($size.Height, $TileHeight * $scale))
              $g.DrawString($text, $font, $brushText, $tx, $ty)
            }
          }
        } finally {
          $pen.Dispose(); $brushBg.Dispose(); $brushText.Dispose(); $font.Dispose()
        }
      } finally {
        $g.Dispose()
      }
      $safe = Get-SafeFileName (($ImageEntry.sourceCategory + "_" + $ImageEntry.sourceMod + "_" + $ImageEntry.fileName))
      $out = Join-Path $OutputRoot ((Get-ShortHash $ImageEntry.copiedPath) + "_" + $safe + ".png")
      $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
      $bmp.Dispose()
      return $out
    } finally {
      $src.Dispose()
    }
  } catch {
    return $null
  }
}

Ensure-Directory $DatabaseRoot
Ensure-Directory $ReportsRoot
Ensure-Directory $PreviewsRoot
Ensure-Directory $WorkingRoot
Ensure-Directory $TilesheetPreviewRoot

foreach ($required in @($InventoryPath, $ReferenceIndexPath, $AuditSummaryPath, $UnresolvedPath, $RepairPlanPath)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required previous mission file missing: $required" }
}

$inventoryDoc = Get-Content -LiteralPath $InventoryPath -Raw | ConvertFrom-Json
$referenceIndex = Get-Content -LiteralPath $ReferenceIndexPath -Raw | ConvertFrom-Json
$repairPlan = Get-Content -LiteralPath $RepairPlanPath -Raw | ConvertFrom-Json
$null = Get-Content -LiteralPath $AuditSummaryPath -Raw
$null = Get-Content -LiteralPath $UnresolvedPath -Raw

$inventoryFiles = @($inventoryDoc.files)
$indexFiles = @($referenceIndex.files)
$fileByCopied = @{}
$fileByOriginal = @{}
$lookups = @{ byFileName = @{}; byCopied = @{} }
foreach ($f in $indexFiles) {
  $fileByCopied[[string]$f.copiedPath] = $f
  $fileByOriginal[([string]$f.originalPath).ToLowerInvariant()] = $f
  $lookups.byCopied[([string]$f.copiedPath).ToLowerInvariant()] = $f
  Add-ListValue $lookups.byFileName ([string]$f.fileName).ToLowerInvariant() $f
}

$planByFile = @{}
foreach ($entry in @($repairPlan.entries)) {
  Add-ListValue $planByFile ([string]$entry.referencingFile).ToLowerInvariant() $entry
}

$mapInventory = @($inventoryFiles | Where-Object { $_.fileType -eq "map" -and ($_.extension -eq ".tmx" -or $_.extension -eq ".tmj") })
$tilesetInventory = @($inventoryFiles | Where-Object { $_.fileType -eq "tileset" })
$imageInventory = @($inventoryFiles | Where-Object { $_.fileType -eq "tilesheet" -and $imageExts -contains $_.extension })

$mapCatalog = New-Object System.Collections.Generic.List[object]
$tileUsage = @{}
$tilesheetUsageByPath = @{}
$mapLayerUsage = @{}
$parseFailures = New-Object System.Collections.Generic.List[object]

foreach ($mapFile in $mapInventory) {
  $mapId = New-MapId $mapFile
  $planItems = if ($planByFile.ContainsKey(([string]$mapFile.originalPath).ToLowerInvariant())) { @($planByFile[([string]$mapFile.originalPath).ToLowerInvariant()].ToArray()) } else { @() }
  $trueMissingCount = @($planItems | Where-Object classification -eq "true_missing").Count
  $ambiguousCount = @($planItems | Where-Object classification -eq "likely_path_error").Count
  $dependencyStatus = Get-DependencyStatus ([string]$mapFile.originalPath) $planByFile
  $baseMap = [ordered]@{
    mapId = $mapId
    sourceCategory = [string]$mapFile.sourceCategory
    sourceMod = [string]$mapFile.sourceMod
    originalPath = [string]$mapFile.originalPath
    copiedPath = [string]$mapFile.copiedPath
    mapFormat = ([string]$mapFile.extension).TrimStart(".")
    mapWidth = $null
    mapHeight = $null
    tileWidth = $null
    tileHeight = $null
    layerNames = @()
    layerTypes = @()
    objectLayerNames = @()
    tilesetsReferenced = @()
    imageLayers = @()
    mapProperties = @{}
    warpRelatedProperties = @{}
    customProperties = @{}
    parseStatus = "failed"
    dependencyStatus = $dependencyStatus
    learningPriority = "exclude"
    notes = ""
  }
  try {
    $ext = ([string]$mapFile.extension).ToLowerInvariant()
    $mapTilesets = New-Object System.Collections.Generic.List[object]
    $layerSummaries = New-Object System.Collections.Generic.List[object]
    if ($ext -eq ".tmx") {
      [xml]$xml = Get-Content -LiteralPath ([string]$mapFile.copiedPath) -Raw
      $mapNode = $xml.map
      $baseMap.mapWidth = [int](Get-XmlAttr $mapNode "width")
      $baseMap.mapHeight = [int](Get-XmlAttr $mapNode "height")
      $baseMap.tileWidth = [int](Get-XmlAttr $mapNode "tilewidth")
      $baseMap.tileHeight = [int](Get-XmlAttr $mapNode "tileheight")
      $baseMap.mapProperties = Get-PropertyMapFromXml $mapNode
      if (Test-WarpProperty $baseMap.mapProperties) { $baseMap.warpRelatedProperties = $baseMap.mapProperties }
      foreach ($ts in $mapNode.SelectNodes("tileset")) {
        $imageSource = $null; $imageWidth = $null; $imageHeight = $null
        $imageNode = $ts.SelectSingleNode("image")
        if ($imageNode) {
          $imageSource = Get-XmlAttr $imageNode "source"
          $imageWidth = if (Get-XmlAttr $imageNode "width") { [int](Get-XmlAttr $imageNode "width") } else { $null }
          $imageHeight = if (Get-XmlAttr $imageNode "height") { [int](Get-XmlAttr $imageNode "height") } else { $null }
        }
        $imageEntry = if ($imageSource) { Resolve-ImageEntry $imageSource $mapFile $lookups } else { $null }
        $tsObj = [pscustomobject]@{
          firstgid = [uint32](Get-XmlAttr $ts "firstgid")
          name = Get-XmlAttr $ts "name"
          source = Get-XmlAttr $ts "source"
          imageSource = $imageSource
          imagePath = if ($imageEntry) { $imageEntry.copiedPath } else { $null }
          tileWidth = if (Get-XmlAttr $ts "tilewidth") { [int](Get-XmlAttr $ts "tilewidth") } else { $baseMap.tileWidth }
          tileHeight = if (Get-XmlAttr $ts "tileheight") { [int](Get-XmlAttr $ts "tileheight") } else { $baseMap.tileHeight }
          tileCount = if (Get-XmlAttr $ts "tilecount") { [int](Get-XmlAttr $ts "tilecount") } else { $null }
          columns = if (Get-XmlAttr $ts "columns") { [int](Get-XmlAttr $ts "columns") } else { $null }
          imageWidth = $imageWidth
          imageHeight = $imageHeight
        }
        $mapTilesets.Add($tsObj)
        $baseMap.tilesetsReferenced += $tsObj
      }
      foreach ($imgLayer in $mapNode.SelectNodes("imagelayer")) {
        $imgNode = $imgLayer.SelectSingleNode("image")
        $baseMap.imageLayers += [pscustomobject]@{ name = Get-XmlAttr $imgLayer "name"; source = if ($imgNode) { Get-XmlAttr $imgNode "source" } else { $null } }
      }
      $sortedMapTilesets = @($mapTilesets.ToArray() | Sort-Object firstgid)
      foreach ($og in $mapNode.SelectNodes("objectgroup")) {
        $baseMap.objectLayerNames += (Get-XmlAttr $og "name")
        $baseMap.layerNames += (Get-XmlAttr $og "name")
        $baseMap.layerTypes += "objectgroup"
      }
      foreach ($layer in $mapNode.SelectNodes("layer")) {
        $layerName = Get-XmlAttr $layer "name"
        $baseMap.layerNames += $layerName
        $baseMap.layerTypes += "tilelayer"
        $layerProps = Get-PropertyMapFromXml $layer
        if (Test-WarpProperty $layerProps) { $baseMap.warpRelatedProperties[$layerName] = $layerProps }
        $gids = @(Decode-TmxData $layer.data)
        $w = if (Get-XmlAttr $layer "width") { [int](Get-XmlAttr $layer "width") } else { [int]$baseMap.mapWidth }
        $h = if (Get-XmlAttr $layer "height") { [int](Get-XmlAttr $layer "height") } else { [int]$baseMap.mapHeight }
        $nonZero = 0
        $layerTileCounts = @{}
        $cellKeys = New-Object 'object[]' $gids.Count
        for ($i = 0; $i -lt $gids.Count; $i++) {
          $rawGid = [uint32]$gids[$i]
          $cleanGid = [uint32]($rawGid -band $gidFlipMask)
          if ($cleanGid -eq 0) { continue }
          $nonZero++
          $x = $i % $w; $y = [Math]::Floor($i / $w)
          $resolved = Resolve-GidTileset $cleanGid $sortedMapTilesets
          $ts = if ($resolved) { $resolved.tileset } else { $null }
          $localId = if ($resolved) { $resolved.localTileId } else { [int]$cleanGid }
          $imageName = if ($ts -and $ts.imageSource) { [IO.Path]::GetFileName($ts.imageSource) } elseif ($ts) { $ts.name } else { "unresolved_gid" }
          $imagePath = if ($ts) { $ts.imagePath } else { $null }
          $tileKey = if ($imagePath) {
            ([string]$imagePath).ToLowerInvariant() + "#" + $localId
          } else {
            "$($mapFile.sourceCategory)|$($mapFile.sourceMod)|$imageName#$localId"
          }
          $cellKeys[$i] = $tileKey
          Add-Count $layerTileCounts $tileKey
          if ($imagePath) {
            Add-Count $tilesheetUsageByPath ([string]$imagePath)
          }
          Add-TileObservation $tileUsage $tileKey ([pscustomobject]@{
            sourceCategory = [string]$mapFile.sourceCategory
            sourceMod = [string]$mapFile.sourceMod
            tilesetName = if ($ts) { $ts.name } else { "unresolved" }
            imageName = $imageName
            localTileId = $localId
            globalTileId = $cleanGid
            copiedImagePath = $imagePath
            mapId = $mapId
            layerName = $layerName
            x = $x
            y = $y
            nearEdge = ($x -le 1 -or $y -le 1 -or $x -ge ($w - 2) -or $y -ge ($h - 2))
            nearWarpLayer = ($layerName -match '(?i)warp|door|path')
            existingProperties = @{}
            existingTerrainData = @()
            existingWangData = @()
          })
        }
        Add-NeighborEvidence $tileUsage $cellKeys $w $h
        $layerSummaries.Add([pscustomobject]@{ layerName = $layerName; nonZeroTiles = $nonZero; uniqueTiles = $layerTileCounts.Keys.Count })
      }
    } else {
      $json = Get-Content -LiteralPath ([string]$mapFile.copiedPath) -Raw | ConvertFrom-Json
      $baseMap.mapWidth = [int]$json.width
      $baseMap.mapHeight = [int]$json.height
      $baseMap.tileWidth = [int]$json.tilewidth
      $baseMap.tileHeight = [int]$json.tileheight
      $baseMap.mapProperties = @{}
      foreach ($p in @($json.properties)) { if ($p.name) { $baseMap.mapProperties[[string]$p.name] = $p.value } }
      if (Test-WarpProperty $baseMap.mapProperties) { $baseMap.warpRelatedProperties = $baseMap.mapProperties }
      foreach ($ts in @($json.tilesets)) {
        $imageSource = if ($ts.image) { [string]$ts.image } else { $null }
        $imageEntry = if ($imageSource) { Resolve-ImageEntry $imageSource $mapFile $lookups } else { $null }
        $tsObj = [pscustomobject]@{
          firstgid = [uint32]$ts.firstgid
          name = if ($ts.name) { [string]$ts.name } else { [IO.Path]::GetFileNameWithoutExtension([string]$ts.source) }
          source = if ($ts.source) { [string]$ts.source } else { $null }
          imageSource = $imageSource
          imagePath = if ($imageEntry) { $imageEntry.copiedPath } else { $null }
          tileWidth = if ($ts.tilewidth) { [int]$ts.tilewidth } else { $baseMap.tileWidth }
          tileHeight = if ($ts.tileheight) { [int]$ts.tileheight } else { $baseMap.tileHeight }
          tileCount = if ($ts.tilecount) { [int]$ts.tilecount } else { $null }
          columns = if ($ts.columns) { [int]$ts.columns } else { $null }
          imageWidth = if ($ts.imagewidth) { [int]$ts.imagewidth } else { $null }
          imageHeight = if ($ts.imageheight) { [int]$ts.imageheight } else { $null }
        }
        $mapTilesets.Add($tsObj)
        $baseMap.tilesetsReferenced += $tsObj
      }
      $sortedMapTilesets = @($mapTilesets.ToArray() | Sort-Object firstgid)
      foreach ($layer in @($json.layers)) {
        $layerName = [string]$layer.name
        $baseMap.layerNames += $layerName
        $baseMap.layerTypes += [string]$layer.type
        if ($layer.type -eq "objectgroup") { $baseMap.objectLayerNames += $layerName; continue }
        if ($layer.type -eq "imagelayer") { $baseMap.imageLayers += [pscustomobject]@{ name = $layerName; source = if ($layer.image) { [string]$layer.image } else { $null } }; continue }
        if ($layer.type -ne "tilelayer") { continue }
        $w = if ($layer.width) { [int]$layer.width } else { [int]$baseMap.mapWidth }
        $h = if ($layer.height) { [int]$layer.height } else { [int]$baseMap.mapHeight }
        $nonZero = 0
        $layerTileCounts = @{}
        $gids = @($layer.data)
        $cellKeys = New-Object 'object[]' $gids.Count
        for ($i = 0; $i -lt $gids.Count; $i++) {
          $rawGid = [uint32]$gids[$i]
          $cleanGid = [uint32]($rawGid -band $gidFlipMask)
          if ($cleanGid -eq 0) { continue }
          $nonZero++
          $x = $i % $w; $y = [Math]::Floor($i / $w)
          $resolved = Resolve-GidTileset $cleanGid $sortedMapTilesets
          $ts = if ($resolved) { $resolved.tileset } else { $null }
          $localId = if ($resolved) { $resolved.localTileId } else { [int]$cleanGid }
          $imageName = if ($ts -and $ts.imageSource) { [IO.Path]::GetFileName($ts.imageSource) } elseif ($ts) { $ts.name } else { "unresolved_gid" }
          $imagePath = if ($ts) { $ts.imagePath } else { $null }
          $tileKey = if ($imagePath) { ([string]$imagePath).ToLowerInvariant() + "#" + $localId } else { "$($mapFile.sourceCategory)|$($mapFile.sourceMod)|$imageName#$localId" }
          $cellKeys[$i] = $tileKey
          Add-Count $layerTileCounts $tileKey
          if ($imagePath) { Add-Count $tilesheetUsageByPath ([string]$imagePath) }
          Add-TileObservation $tileUsage $tileKey ([pscustomobject]@{
            sourceCategory = [string]$mapFile.sourceCategory; sourceMod = [string]$mapFile.sourceMod
            tilesetName = if ($ts) { $ts.name } else { "unresolved" }; imageName = $imageName
            localTileId = $localId; globalTileId = $cleanGid; copiedImagePath = $imagePath
            mapId = $mapId; layerName = $layerName; x = $x; y = $y
            nearEdge = ($x -le 1 -or $y -le 1 -or $x -ge ($w - 2) -or $y -ge ($h - 2))
            nearWarpLayer = ($layerName -match '(?i)warp|door|path')
            existingProperties = @{}; existingTerrainData = @(); existingWangData = @()
          })
        }
        Add-NeighborEvidence $tileUsage $cellKeys $w $h
        $layerSummaries.Add([pscustomobject]@{ layerName = $layerName; nonZeroTiles = $nonZero; uniqueTiles = $layerTileCounts.Keys.Count })
      }
    }
    $baseMap.customProperties = $baseMap.mapProperties
    $baseMap.parseStatus = "parsed"
    $baseMap.learningPriority = Get-LearningPriority ([pscustomobject]$baseMap) $dependencyStatus $trueMissingCount $ambiguousCount
    $baseMap.notes = "Parsed; dependency status from Mission 2 repair plan. Layer usage extracted without visual classification."
    $mapLayerUsage[$mapId] = @($layerSummaries.ToArray())
  } catch {
    $baseMap.parseStatus = "failed"
    $baseMap.learningPriority = "exclude"
    $baseMap.notes = "Parse failed: $($_.Exception.Message) at $($_.InvocationInfo.ScriptLineNumber)"
    $parseFailures.Add([pscustomobject]@{ mapId = $mapId; copiedPath = $mapFile.copiedPath; error = $_.Exception.Message })
  }
  $mapCatalog.Add([pscustomobject]$baseMap)
}

$tilesetCatalog = New-Object System.Collections.Generic.List[object]
$tilesetByImage = @{}

foreach ($tsx in $tilesetInventory) {
  $props = @{}; $imagePath = $null; $imageWidth = $null; $imageHeight = $null
  $tileWidth = $null; $tileHeight = $null; $columns = $null; $tileCount = $null
  $hasTileProperties = $false; $hasObjectGroups = $false; $hasTerrainSets = $false; $hasWangSets = $false
  try {
    [xml]$xml = Get-Content -LiteralPath ([string]$tsx.copiedPath) -Raw
    $tsNode = $xml.tileset
    $tileWidth = if (Get-XmlAttr $tsNode "tilewidth") { [int](Get-XmlAttr $tsNode "tilewidth") } else { $null }
    $tileHeight = if (Get-XmlAttr $tsNode "tileheight") { [int](Get-XmlAttr $tsNode "tileheight") } else { $null }
    $columns = if (Get-XmlAttr $tsNode "columns") { [int](Get-XmlAttr $tsNode "columns") } else { $null }
    $tileCount = if (Get-XmlAttr $tsNode "tilecount") { [int](Get-XmlAttr $tsNode "tilecount") } else { $null }
    $tsxImageNode = $tsNode.SelectSingleNode("image")
    if ($tsxImageNode) {
      $imgEntry = Resolve-ImageEntry (Get-XmlAttr $tsxImageNode "source") $tsx $lookups
      $imagePath = if ($imgEntry) { $imgEntry.copiedPath } else { $null }
      $imageWidth = if (Get-XmlAttr $tsxImageNode "width") { [int](Get-XmlAttr $tsxImageNode "width") } else { $null }
      $imageHeight = if (Get-XmlAttr $tsxImageNode "height") { [int](Get-XmlAttr $tsxImageNode "height") } else { $null }
    }
    $hasTileProperties = [bool]($tsNode.SelectSingleNode("tile/properties"))
    $hasObjectGroups = [bool]($tsNode.SelectSingleNode("tile/objectgroup"))
    $hasTerrainSets = [bool]($tsNode.SelectSingleNode("terraintypes"))
    $hasWangSets = [bool]($tsNode.SelectSingleNode("wangsets"))
  } catch {}
  $used = if ($imagePath -and $tilesheetUsageByPath.ContainsKey($imagePath)) { [int]$tilesheetUsageByPath[$imagePath] } else { 0 }
  $catalogEntry = [pscustomobject]@{
    tilesetId = (Get-ShortHash ([string]$tsx.copiedPath)) + "_" + [IO.Path]::GetFileNameWithoutExtension([string]$tsx.fileName)
    sourceCategory = [string]$tsx.sourceCategory; sourceMod = [string]$tsx.sourceMod
    originalPath = [string]$tsx.originalPath; copiedPath = [string]$tsx.copiedPath
    imagePath = $imagePath; tileWidth = $tileWidth; tileHeight = $tileHeight
    imageWidth = $imageWidth; imageHeight = $imageHeight; columns = $columns; tileCount = $tileCount
    hasTSXMetadata = $true; hasTileProperties = $hasTileProperties; hasObjectGroups = $hasObjectGroups
    hasTerrainSets = $hasTerrainSets; hasWangSets = $hasWangSets
    usedByMaps = $used; commonLayerUsage = @{}
    dependencyStatus = "fully_local"; classificationStatus = "unclassified"
    notes = "External TSX metadata found."
  }
  $tilesetCatalog.Add($catalogEntry)
  if ($imagePath) { $tilesetByImage[$imagePath] = $catalogEntry }
}

foreach ($img in $imageInventory) {
  $dims = Get-ImageDimensions ([string]$img.copiedPath)
  $tileWidth = 16; $tileHeight = 16
  $columns = if ($dims) { [Math]::Floor($dims.width / $tileWidth) } else { $null }
  $tileCount = if ($dims -and $columns -gt 0) { $columns * [Math]::Floor($dims.height / $tileHeight) } else { $null }
  $layerCounts = @{}
  foreach ($tu in $tileUsage.Values) {
    if ($tu.copiedImagePath -eq $img.copiedPath) {
      foreach ($ln in $tu.observedLayers.Keys) { Add-Count $layerCounts $ln ([int]$tu.observedLayers[$ln]) }
    }
  }
  $used = if ($tilesheetUsageByPath.ContainsKey([string]$img.copiedPath)) { [int]$tilesheetUsageByPath[[string]$img.copiedPath] } else { 0 }
  $hasTsx = $tilesetByImage.ContainsKey([string]$img.copiedPath)
  $tilesetCatalog.Add([pscustomobject]@{
    tilesetId = (Get-ShortHash ([string]$img.copiedPath)) + "_" + [IO.Path]::GetFileNameWithoutExtension([string]$img.fileName)
    sourceCategory = [string]$img.sourceCategory; sourceMod = [string]$img.sourceMod
    originalPath = [string]$img.originalPath; copiedPath = [string]$img.copiedPath
    imagePath = [string]$img.copiedPath; tileWidth = $tileWidth; tileHeight = $tileHeight
    imageWidth = if ($dims) { $dims.width } else { $null }; imageHeight = if ($dims) { $dims.height } else { $null }
    columns = $columns; tileCount = $tileCount
    hasTSXMetadata = $hasTsx; hasTileProperties = $false; hasObjectGroups = $false; hasTerrainSets = $false; hasWangSets = $false
    usedByMaps = $used; commonLayerUsage = $layerCounts
    dependencyStatus = if ($used -gt 0) { "observed_local" } else { "not_observed_in_parseable_maps" }
    classificationStatus = "unclassified"
    notes = if ($hasTsx) { "Tilesheet image also has TSX metadata entry." } else { "Image-only tilesheet; no TSX metadata invented." }
  })
}

$layerUsageEntries = New-Object System.Collections.Generic.List[object]
$tileDatabase = New-Object System.Collections.Generic.List[object]
foreach ($tu in $tileUsage.Values) {
  $evidence = Get-EvidenceLabel $tu.observedLayers
  $topNeighbors = @($tu.neighborCounts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 20 | ForEach-Object { [pscustomobject]@{ tileKey = $_.Key; count = $_.Value } })
  $layerUsageEntries.Add([pscustomobject]@{
    tileKey = $tu.tileKey
    copiedImagePath = $tu.copiedImagePath
    sourceCategory = $tu.sourceCategory
    sourceMod = $tu.sourceMod
    tilesetName = $tu.tilesetName
    imageName = $tu.imageName
    localTileId = $tu.localTileId
    observedLayers = $tu.observedLayers
    observedCount = $tu.observedCount
    coordinateExamples = @($tu.coordinateExamples)
    nearMapEdgeCount = $tu.nearEdgeCount
    nearDoorOrWarpLayerCount = $tu.nearWarpLayerCount
    commonNeighbors = $topNeighbors
    evidenceLabel = $evidence.label
    confidence = $evidence.confidence
    reason = $evidence.reason
  })
  $tileDatabase.Add([pscustomobject]@{
    sourceCategory = $tu.sourceCategory
    sourceMod = $tu.sourceMod
    tilesetName = $tu.tilesetName
    imageName = $tu.imageName
    localTileId = $tu.localTileId
    globalTileIdsUsed = $tu.globalTileIdsUsed
    copiedImagePath = $tu.copiedImagePath
    sourceMapsUsedBy = $tu.sourceMapsUsedBy.Keys
    observedLayers = $tu.observedLayers
    observedCount = $tu.observedCount
    neighborEvidence = $topNeighbors
    existingProperties = $tu.existingProperties
    existingTerrainData = $tu.existingTerrainData
    existingWangData = $tu.existingWangData
    evidenceLabel = $evidence.label
    confidence = $evidence.confidence
    approved = $false
    needsHumanReview = $true
    finalClass = $null
    allowedLayers = @()
    collision = "unknown"
    purpose = "unknown"
    notes = "Skeleton entry from parsed map layer usage only; no visual classification."
  })
}

$previewCandidates = @($tilesetCatalog |
  Where-Object { $_.imagePath -and (Test-Path -LiteralPath $_.imagePath -PathType Leaf) } |
  Sort-Object @{ Expression = { if ($_.sourceCategory -eq "moonvillage") { 0 } else { 1 } } }, @{ Expression = "usedByMaps"; Descending = $true } |
  Select-Object -First 40)
$previewRecords = New-Object System.Collections.Generic.List[object]
foreach ($candidate in $previewCandidates) {
  $preview = Generate-Preview $candidate $TilesheetPreviewRoot 16 16
  if ($preview) {
    $previewRecords.Add([pscustomobject]@{ imagePath = $candidate.imagePath; previewPath = $preview; usedByMaps = $candidate.usedByMaps; sourceCategory = $candidate.sourceCategory; sourceMod = $candidate.sourceMod })
  }
}

$mapCatalog | ConvertTo-Json -Depth 18 | Set-Content -LiteralPath (Join-Path $DatabaseRoot "map_catalog.json") -Encoding UTF8
$tilesetCatalog | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $DatabaseRoot "tileset_catalog.json") -Encoding UTF8
$layerUsageEntries | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $DatabaseRoot "layer_usage_index.json") -Encoding UTF8
$tileDatabase | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $DatabaseRoot "tile_database_skeleton.json") -Encoding UTF8
$previewRecords | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $WorkingRoot "preview_manifest.json") -Encoding UTF8

$summary = New-Object System.Collections.Generic.List[string]
$summary.Add("# Mission 3 Tile Intelligence Summary")
$summary.Add("")
$summary.Add("- Generated: $(Get-Date -Format s)")
$summary.Add("- Total maps scanned: $($mapCatalog.Count)")
$summary.Add("- Total maps parsed successfully: $(@($mapCatalog | Where-Object parseStatus -eq 'parsed').Count)")
$summary.Add("- Failed maps: $(@($mapCatalog | Where-Object parseStatus -eq 'failed').Count)")
$summary.Add("")
$summary.Add("## Maps By Dependency Status")
foreach ($g in ($mapCatalog | Group-Object dependencyStatus | Sort-Object Name)) { $summary.Add("- $($g.Name): $($g.Count)") }
$summary.Add("")
$summary.Add("## Maps By Learning Priority")
foreach ($g in ($mapCatalog | Group-Object learningPriority | Sort-Object Name)) { $summary.Add("- $($g.Name): $($g.Count)") }
$summary.Add("")
$summary.Add("- Total tilesheets/images cataloged: $($tilesetCatalog.Count)")
$summary.Add("- Tilesets with TSX metadata: $(@($tilesetCatalog | Where-Object hasTSXMetadata).Count)")
$summary.Add("- Tilesheets without TSX metadata: $(@($tilesetCatalog | Where-Object { -not $_.hasTSXMetadata }).Count)")
$summary.Add("- Total unique tile IDs observed: $($tileDatabase.Count)")
$summary.Add("- Preview contact sheets generated: $($previewRecords.Count)")
$summary.Add("")
$summary.Add("## Recommended Next Mission")
$summary.Add("Review high- and medium-priority maps, then manually approve a small set of tilesheet previews before assigning final tile purposes.")
$summary | Set-Content -LiteralPath (Join-Path $ReportsRoot "mission_3_tile_intelligence_summary.md") -Encoding UTF8

$usable = New-Object System.Collections.Generic.List[string]
$usable.Add("# Usable Maps Report")
$usable.Add("")
foreach ($priority in @("high", "medium", "low", "exclude")) {
  $usable.Add("## $priority")
  foreach ($m in ($mapCatalog | Where-Object learningPriority -eq $priority | Sort-Object sourceCategory, sourceMod, mapId | Select-Object -First 250)) {
    $usable.Add("- $($m.sourceCategory) / $($m.sourceMod) / $($m.mapId): $($m.dependencyStatus) - $($m.notes)")
    $usable.Add("  - $($m.copiedPath)")
  }
  $count = @($mapCatalog | Where-Object learningPriority -eq $priority).Count
  if ($count -gt 250) { $usable.Add("- ... $($count - 250) more omitted from Markdown; see map_catalog.json.") }
  $usable.Add("")
}
$usable | Set-Content -LiteralPath (Join-Path $ReportsRoot "usable_maps_report.md") -Encoding UTF8

$priorityReport = New-Object System.Collections.Generic.List[string]
$priorityReport.Add("# Tilesheet Priority Report")
$priorityReport.Add("")
$priorityReport.Add("## Most-Used Tilesheets")
foreach ($ts in ($tilesetCatalog | Where-Object imagePath | Sort-Object usedByMaps -Descending | Select-Object -First 50)) {
  $priorityReport.Add("- $($ts.usedByMaps) uses: $($ts.sourceCategory) / $($ts.sourceMod) / $([IO.Path]::GetFileName([string]$ts.imagePath))")
  $priorityReport.Add("  - $($ts.imagePath)")
}
$priorityReport.Add("")
$priorityReport.Add("## Moon Village Tilesheets")
foreach ($ts in ($tilesetCatalog | Where-Object { $_.sourceCategory -eq "moonvillage" } | Sort-Object usedByMaps -Descending | Select-Object -First 80)) {
  $priorityReport.Add("- $($ts.usedByMaps) uses: $([IO.Path]::GetFileName([string]$ts.imagePath)) - $($ts.notes)")
}
$priorityReport.Add("")
$priorityReport.Add("## Reference Tilesheets With Strong Map Usage")
foreach ($ts in ($tilesetCatalog | Where-Object { $_.sourceCategory -eq "reference_mods" -and $_.usedByMaps -gt 0 } | Sort-Object usedByMaps -Descending | Select-Object -First 80)) {
  $priorityReport.Add("- $($ts.usedByMaps) uses: $($ts.sourceMod) / $([IO.Path]::GetFileName([string]$ts.imagePath))")
}
$priorityReport.Add("")
$priorityReport.Add("## Tilesheets That Need Manual Tagging First")
foreach ($ts in ($tilesetCatalog | Where-Object { $_.usedByMaps -gt 0 -and -not $_.hasTSXMetadata } | Sort-Object usedByMaps -Descending | Select-Object -First 80)) {
  $priorityReport.Add("- $($ts.usedByMaps) uses, no TSX metadata: $($ts.sourceCategory) / $($ts.sourceMod) / $([IO.Path]::GetFileName([string]$ts.imagePath))")
}
$priorityReport.Add("")
$priorityReport.Add("## Tilesheets That Appear Unused")
foreach ($ts in ($tilesetCatalog | Where-Object { $_.usedByMaps -eq 0 } | Sort-Object sourceCategory, sourceMod | Select-Object -First 120)) {
  $priorityReport.Add("- $($ts.sourceCategory) / $($ts.sourceMod): $($ts.copiedPath)")
}
$unusedCount = @($tilesetCatalog | Where-Object { $_.usedByMaps -eq 0 }).Count
if ($unusedCount -gt 120) { $priorityReport.Add("- ... $($unusedCount - 120) more unused entries omitted from Markdown; see tileset_catalog.json.") }
$priorityReport | Set-Content -LiteralPath (Join-Path $ReportsRoot "tilesheet_priority_report.md") -Encoding UTF8

Write-Output "Maps scanned: $($mapCatalog.Count); parsed: $(@($mapCatalog | Where-Object parseStatus -eq 'parsed').Count); failed: $($parseFailures.Count)"
Write-Output "Tilesheets cataloged: $($tilesetCatalog.Count); unique tile entries: $($tileDatabase.Count)"
Write-Output "Preview contact sheets: $($previewRecords.Count)"
