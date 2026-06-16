Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ToolRoot = $PSScriptRoot
$CandidatePath = Join-Path $ToolRoot "working\preview_candidates.json"
$PreviewRoot = Join-Path $ToolRoot "previews\tilesheets"
New-Item -ItemType Directory -Force -Path $PreviewRoot | Out-Null
Add-Type -AssemblyName System.Drawing

function Get-SafeName([string]$Name) {
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

$candidates = Get-Content -LiteralPath $CandidatePath -Raw | ConvertFrom-Json
$manifest = New-Object System.Collections.Generic.List[object]
$index = 0
foreach ($candidate in $candidates) {
  $index++
  $imagePath = [string]$candidate.imagePath
  if (-not (Test-Path -LiteralPath $imagePath -PathType Leaf)) { continue }
  try {
    $src = [System.Drawing.Bitmap]::FromFile($imagePath)
    try {
      $tileWidth = if ($candidate.tileWidth) { [int]$candidate.tileWidth } else { 16 }
      $tileHeight = if ($candidate.tileHeight) { [int]$candidate.tileHeight } else { 16 }
      if ($src.Width -lt $tileWidth -or $src.Height -lt $tileHeight) { continue }
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
          $cols = [Math]::Floor($src.Width / $tileWidth)
          $rows = [Math]::Floor($src.Height / $tileHeight)
          for ($y = 0; $y -le $rows; $y++) { $g.DrawLine($pen, 0, $y * $tileHeight * $scale, $outW, $y * $tileHeight * $scale) }
          for ($x = 0; $x -le $cols; $x++) { $g.DrawLine($pen, $x * $tileWidth * $scale, 0, $x * $tileWidth * $scale, $outH) }
          for ($row = 0; $row -lt $rows; $row++) {
            for ($col = 0; $col -lt $cols; $col++) {
              $id = $row * $cols + $col
              $tx = $col * $tileWidth * $scale
              $ty = $row * $tileHeight * $scale
              $text = [string]$id
              $size = $g.MeasureString($text, $font)
              $g.FillRectangle($brushBg, $tx, $ty, [Math]::Min($size.Width + 2, $tileWidth * $scale), [Math]::Min($size.Height, $tileHeight * $scale))
              $g.DrawString($text, $font, $brushText, $tx, $ty)
            }
          }
        } finally {
          $pen.Dispose(); $brushBg.Dispose(); $brushText.Dispose(); $font.Dispose()
        }
      } finally {
        $g.Dispose()
      }
      $safe = Get-SafeName ("$($candidate.sourceCategory)_$($candidate.sourceMod)_$([IO.Path]::GetFileName($imagePath))")
      $out = Join-Path $PreviewRoot (("{0:D2}_" -f $index) + (Get-ShortHash $imagePath) + "_" + $safe + ".png")
      $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
      $bmp.Dispose()
      $manifest.Add([pscustomobject]@{
        imagePath = $imagePath
        previewPath = $out
        usedByMaps = $candidate.usedByMaps
        sourceCategory = $candidate.sourceCategory
        sourceMod = $candidate.sourceMod
      })
    } finally {
      $src.Dispose()
    }
  } catch {
    $manifest.Add([pscustomobject]@{
      imagePath = $imagePath
      previewPath = $null
      usedByMaps = $candidate.usedByMaps
      sourceCategory = $candidate.sourceCategory
      sourceMod = $candidate.sourceMod
      error = $_.Exception.Message
    })
  }
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $ToolRoot "working\preview_manifest.json") -Encoding UTF8
Write-Output "Generated $(@($manifest | Where-Object previewPath).Count) preview contact sheets."
