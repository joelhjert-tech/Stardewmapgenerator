Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ToolRoot = $PSScriptRoot
$ManifestPath = Join-Path $ToolRoot "working\review_pack_preview_manifest.json"
$PreviewRoot = Join-Path $ToolRoot "previews\review_packs"
New-Item -ItemType Directory -Force -Path $PreviewRoot | Out-Null
Add-Type -AssemblyName System.Drawing

function Get-PreviewVariantPath([string]$Path, [string]$Suffix) {
  $directory = Split-Path -Parent $Path
  $name = [IO.Path]::GetFileNameWithoutExtension($Path)
  $extension = [IO.Path]::GetExtension($Path)
  return Join-Path $directory "$name`_$Suffix$extension"
}

$packs = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$written = New-Object System.Collections.Generic.List[object]

foreach ($packInfo in $packs) {
  $pack = Get-Content -LiteralPath ([string]$packInfo.packPath) -Raw | ConvertFrom-Json
  $imagePath = [string]$pack.copiedImagePath
  if (-not (Test-Path -LiteralPath $imagePath -PathType Leaf)) { continue }
  try {
    $src = [System.Drawing.Bitmap]::FromFile($imagePath)
    try {
      $tileWidth = 16
      $tileHeight = 16
      $cols = [Math]::Floor($src.Width / $tileWidth)
      $rows = [Math]::Floor($src.Height / $tileHeight)
      if ($cols -le 0 -or $rows -le 0) {
        $outW = [Math]::Max(160, $src.Width * 4)
        $outH = [Math]::Max(80, $src.Height * 4 + 30)
        $bmp = [System.Drawing.Bitmap]::new($outW, $outH)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        try {
          $g.Clear([System.Drawing.Color]::FromArgb(30, 30, 30))
          $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
          $g.DrawImage($src, 8, 8, $src.Width * 4, $src.Height * 4)
          $out = [string]$pack.contactSheetPath
          $cleanOut = Get-PreviewVariantPath $out "clean"
          $labeledOut = Get-PreviewVariantPath $out "labeled"
          New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
          $bmp.Save($cleanOut, [System.Drawing.Imaging.ImageFormat]::Png)
          $font = [System.Drawing.Font]::new("Arial", 9, [System.Drawing.FontStyle]::Regular)
          $brush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
          try { $g.DrawString("No 16x16 grid: $($pack.tilesheetName)", $font, $brush, 8, $src.Height * 4 + 12) }
          finally { $font.Dispose(); $brush.Dispose() }
        } finally {
          $g.Dispose()
        }
        $out = [string]$pack.contactSheetPath
        $labeledOut = Get-PreviewVariantPath $out "labeled"
        $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Save($labeledOut, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        $written.Add([pscustomobject]@{ reviewPackId = $pack.reviewPackId; previewPath = $out; cleanPreviewPath = $cleanOut; labeledPreviewPath = $labeledOut; candidates = $pack.candidateCount; notes = "Source image is smaller than a 16x16 grid." })
        continue
      }

      $scale = if ($src.Width -lt 768) { 2 } else { 1 }
      $maxDim = 4096
      if (($src.Width * $scale) -gt $maxDim -or ($src.Height * $scale) -gt $maxDim) {
        $scale = [Math]::Max(1, [Math]::Floor([Math]::Min($maxDim / $src.Width, $maxDim / $src.Height)))
      }
      $outW = [int]($src.Width * $scale)
      $outH = [int]($src.Height * $scale)
      $bmp = [System.Drawing.Bitmap]::new($outW, $outH)
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      try {
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
        $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
        $g.DrawImage($src, 0, 0, $outW, $outH)
        $out = [string]$pack.contactSheetPath
        $cleanOut = Get-PreviewVariantPath $out "clean"
        $labeledOut = Get-PreviewVariantPath $out "labeled"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
        $bmp.Save($cleanOut, [System.Drawing.Imaging.ImageFormat]::Png)

        $gridPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(135, 255, 255, 255), 1)
        $highPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(230, 255, 40, 40), [Math]::Max(2, 2 * $scale))
        $brushBg = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(170, 0, 0, 0))
        $brushText = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
        $font = [System.Drawing.Font]::new("Arial", [Math]::Max(6, 7 * $scale), [System.Drawing.FontStyle]::Regular)
        try {
          for ($y = 0; $y -le $rows; $y++) { $g.DrawLine($gridPen, 0, $y * $tileHeight * $scale, $outW, $y * $tileHeight * $scale) }
          for ($x = 0; $x -le $cols; $x++) { $g.DrawLine($gridPen, $x * $tileWidth * $scale, 0, $x * $tileWidth * $scale, $outH) }

          $counts = @($pack.candidates | ForEach-Object { [int]$_.observedCountTotal } | Sort-Object -Descending)
          $threshold = if ($counts.Count -gt 0) { [Math]::Max(100, $counts[[Math]::Min(20, $counts.Count - 1)]) } else { 100 }
          if (@($pack.candidates).Count -eq 0) {
            for ($row = 0; $row -lt $rows; $row++) {
              for ($col = 0; $col -lt $cols; $col++) {
                $id = [string]($row * $cols + $col)
                $tx = $col * $tileWidth * $scale
                $ty = $row * $tileHeight * $scale
                $size = $g.MeasureString($id, $font)
                $g.FillRectangle($brushBg, $tx, $ty, [Math]::Min($size.Width + 2, $tileWidth * $scale), [Math]::Min($size.Height, $tileHeight * $scale))
                $g.DrawString($id, $font, $brushText, $tx, $ty)
              }
            }
          }
          foreach ($candidate in $pack.candidates) {
            if ($null -eq $candidate.tileX -or $null -eq $candidate.tileY) { continue }
            $x = [int]$candidate.tileX
            $y = [int]$candidate.tileY
            if ($x -lt 0 -or $y -lt 0 -or $x -ge $cols -or $y -ge $rows) { continue }
            $tx = $x * $tileWidth * $scale
            $ty = $y * $tileHeight * $scale
            $id = if ($null -ne $candidate.localTileId) { [string]$candidate.localTileId } else { "$x,$y" }
            $size = $g.MeasureString($id, $font)
            $g.FillRectangle($brushBg, $tx, $ty, [Math]::Min($size.Width + 2, $tileWidth * $scale), [Math]::Min($size.Height, $tileHeight * $scale))
            $g.DrawString($id, $font, $brushText, $tx, $ty)
            if ([int]$candidate.observedCountTotal -ge $threshold) {
              $g.DrawRectangle($highPen, $tx + 1, $ty + 1, ($tileWidth * $scale) - 2, ($tileHeight * $scale) - 2)
            }
          }
        } finally {
          $gridPen.Dispose(); $highPen.Dispose(); $brushBg.Dispose(); $brushText.Dispose(); $font.Dispose()
        }
      } finally {
        $g.Dispose()
      }
      $out = [string]$pack.contactSheetPath
      $labeledOut = Get-PreviewVariantPath $out "labeled"
      $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
      $bmp.Save($labeledOut, [System.Drawing.Imaging.ImageFormat]::Png)
      $bmp.Dispose()
      $written.Add([pscustomobject]@{ reviewPackId = $pack.reviewPackId; previewPath = $out; cleanPreviewPath = $cleanOut; labeledPreviewPath = $labeledOut; candidates = $pack.candidateCount })
    } finally {
      $src.Dispose()
    }
  } catch {
    $written.Add([pscustomobject]@{ reviewPackId = $pack.reviewPackId; previewPath = $null; error = $_.Exception.Message })
  }
}

$written | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ToolRoot "working\review_pack_preview_results.json") -Encoding UTF8
Write-Output "Generated $(@($written | Where-Object previewPath).Count) review pack preview sheets."
