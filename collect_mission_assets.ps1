Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$MissionRoot = Join-Path $PSScriptRoot "mission_assets"
$ReportsRoot = Join-Path $MissionRoot "reports"
$StardewModsRoot = "C:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Mods"

$mapExts = @(".tmx", ".tmj")
$tilesetExts = @(".tsx")
$imageExts = @(".png", ".ase", ".aseprite", ".bmp", ".jpg", ".jpeg")
$jsonExts = @(".json")
$mapWords = @(
  "map", "maps", "tiled", "tilesheet", "tilesheets", "tileset", "tilesets",
  "location", "locations", "warp", "warps", "minecart", "minecarts",
  "patch", "patches", "festival", "festivals", "farm", "greenhouse",
  "dungeon", "cave", "busstop", "town", "forest", "mountain", "beach"
)
$excludeDirWords = @(
  "dialogue", "dialogues", "portrait", "portraits", "sprite", "sprites",
  "characters", "characterfiles", "schedules", "music", "audio", "sound",
  "sounds", "i18n", "mail", "quests", "weapons", "objects", "crops",
  "shirts", "pants", "hats", "boots", "furniture", "docs", "documentation",
  "savebackup", "saves", "screenshots", "obj", "bin", ".git"
)
$mapJsonRegex = "(?i)(`"Action`"\s*:\s*`"(Load|Edit)Map|`"Target`"\s*:\s*`"Maps/|`"FromFile`"\s*:\s*`"[^`"]+\.(tmx|tmj)|`"MapPath`"|`"MapFile`"|`"AddLocations`"|`"Data/Locations|Warp|Warps|Minecart|TileSheet|Tilesheet|Tilesheets|MapPatches|MapLoads|MapWarps|LocationContext|ExtraMap|EditMap|LoadMap)"

function New-CleanDirectory($Path) {
  if (Test-Path -LiteralPath $Path) {
    try {
      Remove-Item -LiteralPath $Path -Recurse -Force
    } catch {
      [System.IO.Directory]::Delete([System.IO.Path]::GetFullPath($Path), $true)
    }
  }
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Get-ShortHash([string]$Value) {
  $sha1 = [System.Security.Cryptography.SHA1]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $hash = $sha1.ComputeHash($bytes)
    return -join ($hash[0..7] | ForEach-Object { $_.ToString("x2") })
  } finally {
    $sha1.Dispose()
  }
}

function ConvertTo-SafeName([string]$Name) {
  $safe = $Name -replace '[<>:"/\\|?*]', '_'
  $safe = $safe -replace '\s+$', ''
  if ([string]::IsNullOrWhiteSpace($safe)) { return "_unnamed" }
  return $safe
}

function Get-RelativePath([string]$Base, [string]$Path) {
  $baseUri = [Uri](([IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'))
  $pathUri = [Uri]([IO.Path]::GetFullPath($Path))
  return [Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace('/', '\')
}

function Test-PathHasAnyWord([string]$RelativePath, [string[]]$Words) {
  $parts = ($RelativePath -split '[\\/._\-\s\[\]\(\)]+') | Where-Object { $_ }
  foreach ($part in $parts) {
    foreach ($word in $Words) {
      if ($part -ieq $word -or $part -ilike "*$word*") { return $true }
    }
  }
  return $false
}

function Test-IsExcludedContext([string]$RelativePath) {
  return (Test-PathHasAnyWord $RelativePath $excludeDirWords)
}

function Test-IsMapishPath([string]$RelativePath) {
  return (Test-PathHasAnyWord $RelativePath $mapWords)
}

function Read-TextBestEffort([string]$Path) {
  try {
    return Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
  } catch {
    return ""
  }
}

function Get-JsonStringReferences($Value) {
  $refs = New-Object System.Collections.Generic.List[string]
  if ($null -eq $Value) { return $refs }
  if ($Value -is [string]) {
    if ($Value -match '(?i)\.(tmx|tmj|tsx|png|ase|aseprite|bmp|jpe?g)$' -or
        $Value -match '(?i)(Maps/|assets/Maps|TileSheet|Tilesheet|Warp|Location)') {
      $refs.Add($Value)
    }
    return $refs
  }
  if ($Value -is [System.Collections.IDictionary]) {
    foreach ($k in $Value.Keys) {
      foreach ($r in (Get-JsonStringReferences $Value[$k])) { $refs.Add($r) }
    }
    return $refs
  }
  if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
    foreach ($item in $Value) {
      foreach ($r in (Get-JsonStringReferences $item)) { $refs.Add($r) }
    }
  }
  return $refs
}

function Get-ReferencesFromTiledFile([IO.FileInfo]$File) {
  $refs = New-Object System.Collections.Generic.List[string]
  $ext = $File.Extension.ToLowerInvariant()
  if ($ext -eq ".tmx" -or $ext -eq ".tsx") {
    try {
      [xml]$xml = Get-Content -LiteralPath $File.FullName -Raw
      $nodes = $xml.SelectNodes("//*[@source]")
      foreach ($node in $nodes) {
        if ($node.source) { $refs.Add([string]$node.source) }
      }
    } catch {
      $text = Read-TextBestEffort $File.FullName
      foreach ($m in [regex]::Matches($text, '(?i)source="([^"]+\.(tsx|png|ase|aseprite|bmp|jpe?g))"')) {
        $refs.Add($m.Groups[1].Value)
      }
    }
  } elseif ($ext -eq ".tmj") {
    try {
      $json = Get-Content -LiteralPath $File.FullName -Raw | ConvertFrom-Json
      foreach ($ts in @($json.tilesets)) {
        if ($ts.source) { $refs.Add([string]$ts.source) }
        if ($ts.image) { $refs.Add([string]$ts.image) }
      }
    } catch {
      $text = Read-TextBestEffort $File.FullName
      foreach ($m in [regex]::Matches($text, '(?i)"(?:source|image)"\s*:\s*"([^"]+\.(tsx|png|ase|aseprite|bmp|jpe?g))"')) {
        $refs.Add($m.Groups[1].Value)
      }
    }
  }
  return @($refs | Select-Object -Unique)
}

function Resolve-Reference([IO.FileInfo]$FromFile, [string]$Reference, [string]$ModRoot) {
  if ([string]::IsNullOrWhiteSpace($Reference)) { return $null }
  $clean = $Reference -replace '/', '\'
  $clean = [Uri]::UnescapeDataString($clean)
  if ($clean -match '^[a-zA-Z]+:') { return $null }

  $candidates = New-Object System.Collections.Generic.List[string]
  $candidates.Add((Join-Path $FromFile.DirectoryName $clean))
  $trimmed = $clean.TrimStart('\')
  $candidates.Add((Join-Path $ModRoot $trimmed))
  if ($trimmed -match '^(assets|Assets)\\') {
    $candidates.Add((Join-Path $ModRoot $trimmed))
  }
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  $leaf = Split-Path $clean -Leaf
  $lookupKey = $ModRoot.ToLowerInvariant()
  if ($leaf -and $modFileLookups.ContainsKey($lookupKey)) {
    $leafKey = $leaf.ToLowerInvariant()
    $lookup = $modFileLookups[$lookupKey]
    if ($lookup.ContainsKey($leafKey)) {
      return $lookup[$leafKey][0]
    }
  }
  return $null
}

function Get-FileType([IO.FileInfo]$File, [string]$RelativePath) {
  $ext = $File.Extension.ToLowerInvariant()
  if ($mapExts -contains $ext) { return "map" }
  if ($tilesetExts -contains $ext) { return "tileset" }
  if ($imageExts -contains $ext) { return "tilesheet" }
  if ($jsonExts -contains $ext) { return "map_config" }
  return "unknown"
}

function Get-Bucket([string]$FileType) {
  switch ($FileType) {
    "map" { return "maps" }
    "tileset" { return "tilesets" }
    "tilesheet" { return "tilesheets" }
    "map_config" { return "other_map_assets" }
    default { return "other_map_assets" }
  }
}

$inventory = New-Object System.Collections.Generic.List[object]
$missingRefs = New-Object System.Collections.Generic.List[object]
$needsReview = New-Object System.Collections.Generic.List[object]
$copiedByOriginal = @{}
$modFileLookups = @{}
$referencedOriginals = New-Object System.Collections.Generic.HashSet[string]
$queued = New-Object System.Collections.Generic.Queue[object]
$queuedKeys = New-Object System.Collections.Generic.HashSet[string]

function Queue-File([IO.FileInfo]$File, [string]$SourceCategory, [string]$SourceMod, [string]$ModRoot, [string]$Reason, [bool]$Review) {
  $key = $File.FullName.ToLowerInvariant()
  if ($queuedKeys.Add($key)) {
    $queued.Enqueue([pscustomobject]@{
      File = $File
      SourceCategory = $SourceCategory
      SourceMod = $SourceMod
      ModRoot = $ModRoot
      Reason = $Reason
      Review = $Review
    })
  }
}

function Copy-QueuedFile($Item) {
  $file = $Item.File
  $sourceCategory = $Item.SourceCategory
  $sourceMod = $Item.SourceMod
  $modRoot = $Item.ModRoot
  $relative = Get-RelativePath $modRoot $file.FullName
  $fileType = Get-FileType $file $relative
  $bucket = Get-Bucket $fileType
  $safeMod = ConvertTo-SafeName $sourceMod
  if ($Item.Review -and $sourceCategory -eq "stardew_mods") {
    $destRoot = Join-Path $MissionRoot "stardew_mods\_needs_review\$safeMod"
  } elseif ($sourceCategory -eq "moonvillage") {
    $destRoot = Join-Path $MissionRoot "moonvillage\$bucket\$safeMod"
  } else {
    $destRoot = Join-Path $MissionRoot "$sourceCategory\$safeMod\$bucket"
  }
  $dest = Join-Path $destRoot $relative
  if ($dest.Length -gt 240) {
    $hash = Get-ShortHash $relative
    $dest = Join-Path $destRoot ("__long_paths\" + $hash + "_" + $file.Name)
  }
  $destDir = Split-Path $dest -Parent
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null
  Copy-Item -LiteralPath $file.FullName -Destination $dest -Force

  $linked = @()
  if ($fileType -eq "map" -or $fileType -eq "tileset") {
    $linked = @(Get-ReferencesFromTiledFile $file)
  } elseif ($fileType -eq "map_config") {
    try {
      $json = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
      $linked = @(Get-JsonStringReferences $json | Select-Object -Unique)
    } catch {
      $linked = @()
    }
  }

  $entry = [pscustomobject]@{
    sourceCategory = $sourceCategory
    sourceMod = $sourceMod
    originalPath = $file.FullName
    copiedPath = $dest
    fileName = $file.Name
    extension = $file.Extension.ToLowerInvariant()
    fileType = $fileType
    fileSize = $file.Length
    linkedFiles = $linked
    notes = $Item.Reason
  }
  $inventory.Add($entry)
  $copiedByOriginal[$file.FullName.ToLowerInvariant()] = $entry
  if ($Item.Review) {
    $needsReview.Add($entry)
  }

  if ($fileType -eq "map" -or $fileType -eq "tileset") {
    foreach ($ref in $linked) {
      if ($ref -notmatch '(?i)\.(tsx|png|ase|aseprite|bmp|jpe?g)$') { continue }
      $resolved = Resolve-Reference $file $ref $modRoot
      if ($resolved) {
        [void]$referencedOriginals.Add($resolved.ToLowerInvariant())
        if (-not $copiedByOriginal.ContainsKey($resolved.ToLowerInvariant())) {
          Queue-File (Get-Item -LiteralPath $resolved) $sourceCategory $sourceMod $modRoot "referenced by $($file.Name): $ref" $false
        }
      } else {
        $missingRefs.Add([pscustomobject]@{
          sourceCategory = $sourceCategory
          sourceMod = $sourceMod
          referringFile = $file.FullName
          reference = $ref
          notes = "Referenced file could not be found"
        })
      }
    }
  }
}

function Scan-ModRoot([string]$ModRoot, [string]$SourceCategory, [string]$SourceMod) {
  if (-not (Test-Path -LiteralPath $ModRoot -PathType Container)) { return }
  $allFiles = @(Get-ChildItem -LiteralPath $ModRoot -Recurse -File -Force -ErrorAction SilentlyContinue)
  $lookup = @{}
  foreach ($indexedFile in $allFiles) {
    $leafKey = $indexedFile.Name.ToLowerInvariant()
    if (-not $lookup.ContainsKey($leafKey)) {
      $lookup[$leafKey] = New-Object System.Collections.Generic.List[string]
    }
    $lookup[$leafKey].Add($indexedFile.FullName)
  }
  $modFileLookups[$ModRoot.ToLowerInvariant()] = $lookup
  $hasTiledFiles = [bool]($allFiles | Where-Object {
    $mapExts -contains $_.Extension.ToLowerInvariant() -or $_.Extension.ToLowerInvariant() -eq ".tsx"
  } | Select-Object -First 1)
  foreach ($file in $allFiles) {
    $relative = Get-RelativePath $ModRoot $file.FullName
    if ($relative -match '(^|\\)tools\\tiled-map-assistant\\mission_assets(\\|$)') { continue }
    $ext = $file.Extension.ToLowerInvariant()
    $excluded = Test-IsExcludedContext $relative
    if ($mapExts -contains $ext) {
      Queue-File $file $SourceCategory $SourceMod $ModRoot "tiled map file" $false
      continue
    }
    if ($tilesetExts -contains $ext) {
      Queue-File $file $SourceCategory $SourceMod $ModRoot "tiled tileset file" $false
      continue
    }
    if ($imageExts -contains $ext) {
      if ((Test-IsMapishPath $relative) -and -not $excluded) {
        Queue-File $file $SourceCategory $SourceMod $ModRoot "map/tilesheet image by path" $false
      }
      continue
    }
    if ($ext -eq ".json") {
      $name = $file.Name.ToLowerInvariant()
      $pathMapish = Test-IsMapishPath $relative
      $copy = $false
      $reason = ""
      if ($name -eq "content.json") {
        $text = Read-TextBestEffort $file.FullName
        if ($text -match $mapJsonRegex) {
          $copy = $true
          $reason = "Content Patcher map-related content.json"
        }
      } elseif ($name -eq "manifest.json") {
        if ($hasTiledFiles) {
          $copy = $true
          $reason = "manifest for source mod with map assets"
        }
      } elseif ($pathMapish -and -not $excluded) {
        $text = Read-TextBestEffort $file.FullName
        if ($text -match $mapJsonRegex -or $relative -match '(?i)(map|warp|location|tilesheet|minecart)') {
          $copy = $true
          $reason = "map-related json by path/content"
        }
      }
      if ($copy) {
        Queue-File $file $SourceCategory $SourceMod $ModRoot $reason $false
      } elseif ($SourceCategory -eq "stardew_mods" -and $pathMapish -and -not $excluded) {
        Queue-File $file $SourceCategory $SourceMod $ModRoot "uncertain map-like json" $true
      }
    }
  }
}

New-CleanDirectory $MissionRoot
New-Item -ItemType Directory -Force -Path $ReportsRoot | Out-Null
foreach ($path in @(
  "moonvillage\maps", "moonvillage\tilesheets", "moonvillage\tilesets", "moonvillage\other_map_assets",
  "reference_mods", "stardew_mods", "stardew_mods\_needs_review"
)) {
  New-Item -ItemType Directory -Force -Path (Join-Path $MissionRoot $path) | Out-Null
}

$moonRoots = @(
  (Join-Path $Workspace "MainMoonvillage-git"),
  (Join-Path $Workspace "MoonvillageHotelAddon")
) | Where-Object { Test-Path -LiteralPath $_ -PathType Container }
foreach ($root in $moonRoots) {
  Scan-ModRoot $root "moonvillage" (Split-Path $root -Leaf)
}

$referenceRoot = Join-Path $Workspace "Reference mods"
if (Test-Path -LiteralPath $referenceRoot -PathType Container) {
  foreach ($mod in Get-ChildItem -LiteralPath $referenceRoot -Directory -Force) {
    Scan-ModRoot $mod.FullName "reference_mods" $mod.Name
  }
}

if (Test-Path -LiteralPath $StardewModsRoot -PathType Container) {
  foreach ($mod in Get-ChildItem -LiteralPath $StardewModsRoot -Directory -Force) {
    Scan-ModRoot $mod.FullName "stardew_mods" $mod.Name
  }
}

while ($queued.Count -gt 0) {
  $item = $queued.Dequeue()
  if (-not $copiedByOriginal.ContainsKey($item.File.FullName.ToLowerInvariant())) {
    Copy-QueuedFile $item
  }
}

$duplicates = $inventory |
  Group-Object fileName |
  Where-Object { $_.Count -gt 1 } |
  ForEach-Object {
    [pscustomobject]@{
      fileName = $_.Name
      count = $_.Count
      files = @($_.Group | ForEach-Object { $_.originalPath })
    }
  }

$unreferencedTilesheets = @($inventory | Where-Object {
  $_.fileType -eq "tilesheet" -and -not $referencedOriginals.Contains($_.originalPath.ToLowerInvariant())
})

$inventoryJson = [pscustomobject]@{
  generatedAt = (Get-Date).ToString("o")
  missionRoot = $MissionRoot
  sourceRoots = [pscustomobject]@{
    moonvillage = @($moonRoots)
    reference_mods = $referenceRoot
    stardew_mods = $StardewModsRoot
  }
  files = @($inventory.ToArray())
  missingReferences = @($missingRefs.ToArray())
  duplicateFileNames = @($duplicates)
  unreferencedTilesheets = @($unreferencedTilesheets | ForEach-Object { $_.copiedPath })
  needsReview = @($needsReview.ToArray())
}
$inventoryJson | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $ReportsRoot "asset_inventory.json") -Encoding UTF8

$totalMaps = @($inventory | Where-Object fileType -eq "map").Count
$totalTilesets = @($inventory | Where-Object fileType -eq "tileset").Count
$totalTilesheets = @($inventory | Where-Object fileType -eq "tilesheet").Count
$totalConfigs = @($inventory | Where-Object fileType -eq "map_config").Count

$md = New-Object System.Collections.Generic.List[string]
$md.Add("# Tiled Map Assistant Asset Inventory")
$md.Add("")
$md.Add("- Generated: $(Get-Date -Format s)")
$md.Add("- Total maps found: $totalMaps")
$md.Add("- Total tilesets found: $totalTilesets")
$md.Add("- Total tilesheet images found: $totalTilesheets")
$md.Add("- Total map config files found: $totalConfigs")
$md.Add("")
$md.Add("## By Source Category")
foreach ($group in ($inventory | Group-Object sourceCategory | Sort-Object Name)) {
  $md.Add("- $($group.Name): $($group.Count) files")
}
$md.Add("")
$md.Add("## By Mod")
foreach ($category in @("moonvillage", "reference_mods", "stardew_mods")) {
  $md.Add("### $category")
  foreach ($group in ($inventory | Where-Object sourceCategory -eq $category | Group-Object sourceMod | Sort-Object Name)) {
    $maps = @($group.Group | Where-Object fileType -eq "map").Count
    $sets = @($group.Group | Where-Object fileType -eq "tileset").Count
    $imgs = @($group.Group | Where-Object fileType -eq "tilesheet").Count
    $cfg = @($group.Group | Where-Object fileType -eq "map_config").Count
    $md.Add("- $($group.Name): $($group.Count) files ($maps maps, $sets tilesets, $imgs images, $cfg configs)")
  }
  $md.Add("")
}
$md.Add("## Duplicate File Names")
if ($duplicates.Count -eq 0) {
  $md.Add("- None detected.")
} else {
  foreach ($dup in $duplicates | Sort-Object fileName) {
    $md.Add("- $($dup.fileName): $($dup.count) copies")
    foreach ($path in $dup.files) { $md.Add("  - $path") }
  }
}
$md.Add("")
$md.Add("## Map/Tileset Files With Missing Referenced Tilesheets")
if ($missingRefs.Count -eq 0) {
  $md.Add("- None detected.")
} else {
  foreach ($miss in $missingRefs) {
    $md.Add("- $($miss.sourceCategory) / $($miss.sourceMod): $($miss.referringFile) references $($miss.reference)")
  }
}
$md.Add("")
$md.Add("## Tilesheets Not Referenced By A Copied Map/Tileset")
if ($unreferencedTilesheets.Count -eq 0) {
  $md.Add("- None detected.")
} else {
  foreach ($entry in $unreferencedTilesheets | Sort-Object sourceCategory, sourceMod, fileName) {
    $md.Add("- $($entry.sourceCategory) / $($entry.sourceMod): $($entry.copiedPath)")
  }
}
$md.Add("")
$md.Add("## Uncertain Files In _needs_review")
if ($needsReview.Count -eq 0) {
  $md.Add("- None.")
} else {
  foreach ($entry in $needsReview | Sort-Object sourceMod, fileName) {
    $md.Add("- $($entry.sourceMod): $($entry.originalPath) -> $($entry.copiedPath)")
  }
}
$md | Set-Content -LiteralPath (Join-Path $ReportsRoot "asset_inventory.md") -Encoding UTF8

$unusual = New-Object System.Collections.Generic.List[string]
$unusual.Add("# Missing Or Unusual Files")
$unusual.Add("")
$unusual.Add("## Missing References")
if ($missingRefs.Count -eq 0) {
  $unusual.Add("- None detected.")
} else {
  foreach ($miss in $missingRefs) {
    $unusual.Add("- $($miss.sourceCategory) / $($miss.sourceMod): $($miss.referringFile) references $($miss.reference)")
  }
}
$unusual.Add("")
$unusual.Add("## Needs Review")
if ($needsReview.Count -eq 0) {
  $unusual.Add("- None.")
} else {
  foreach ($entry in $needsReview | Sort-Object sourceMod, fileName) {
    $unusual.Add("- $($entry.sourceMod): $($entry.originalPath) copied to $($entry.copiedPath) ($($entry.notes))")
  }
}
$unusual | Set-Content -LiteralPath (Join-Path $ReportsRoot "missing_or_unusual_files.md") -Encoding UTF8

Write-Output "Copied $($inventory.Count) files into $MissionRoot"
Write-Output "Maps: $totalMaps; Tilesets: $totalTilesets; Tilesheet images: $totalTilesheets; Map configs: $totalConfigs"
Write-Output "Missing references: $($missingRefs.Count); Needs review: $($needsReview.Count)"
