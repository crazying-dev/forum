# gen-android-icons.ps1
# Regenerate the Android launcher icons from the project's ORIGINAL logo
# (forum/static/img/favicon.png, 1080x1080 - the same artwork used by the
#  Windows client's icon.ico and by the website header / apple-touch-icon).
#
# Outputs (app/src/main/res):
#   mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png           legacy square
#   mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher_round.png     legacy round
#   mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher_foreground.png adaptive foreground
#
# Requires Windows PowerShell 5.1 + System.Drawing (no extra dependencies).

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$Root   = Split-Path -Parent (Split-Path -Parent $PSCommandPath)   # forum-Android
$Repo   = Split-Path -Parent $Root                                 # workspace root
$Source = Join-Path $Repo 'forum\static\img\favicon.png'
$Res    = Join-Path $Root 'app\src\main\res'

if (-not (Test-Path $Source)) { throw "source logo not found: $Source" }

$src = [System.Drawing.Bitmap]::new((Resolve-Path $Source).Path)

# --- opaque bounding box of the emblem (the artwork has transparent corners) ---
$W = $src.Width; $H = $src.Height
$minX = $W; $minY = $H; $maxX = -1; $maxY = -1
for ($y = 0; $y -lt $H; $y++) {
  for ($x = 0; $x -lt $W; $x++) {
    if ($src.GetPixel($x, $y).A -gt 16) {
      if ($x -lt $minX) { $minX = $x }
      if ($x -gt $maxX) { $maxX = $x }
      if ($y -lt $minY) { $minY = $y }
      if ($y -gt $maxY) { $maxY = $y }
    }
  }
}
$crop = New-Object System.Drawing.Rectangle($minX, $minY, ($maxX - $minX + 1), ($maxY - $minY + 1))
Write-Host ("source {0}x{1}, emblem bbox {2}x{3}" -f $W, $H, $crop.Width, $crop.Height)

function New-Canvas([int]$size) {
  $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
  $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
  $g.Clear([System.Drawing.Color]::Transparent)
  return @($bmp, $g)
}

function Save-Png($bmp, [string]$path) {
  $dir = Split-Path -Parent $path
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
}

# density -> @( legacy px, adaptive canvas px, adaptive content px )
$densities = [ordered]@{
  'mdpi'    = @(48,  108, 66)
  'hdpi'    = @(72,  162, 99)
  'xhdpi'   = @(96,  216, 132)
  'xxhdpi'  = @(144, 324, 198)
  'xxxhdpi' = @(192, 432, 264)
}

foreach ($name in $densities.Keys) {
  $v = $densities[$name]
  $legacyPx = [int]$v[0]; $canvasPx = [int]$v[1]; $contentPx = [int]$v[2]
  $dir = Join-Path $Res ("mipmap-" + $name)

  # legacy square / round icon: whole artwork, transparent corners preserved
  $pair = New-Canvas $legacyPx
  $legacy = $pair[0]; $lg = $pair[1]
  $lg.DrawImage($src, (New-Object System.Drawing.Rectangle(0, 0, $legacyPx, $legacyPx)))
  $lg.Dispose()
  Save-Png $legacy (Join-Path $dir 'ic_launcher.png')
  Save-Png $legacy (Join-Path $dir 'ic_launcher_round.png')
  $legacy.Dispose()

  # adaptive foreground: emblem drawn inside the 66/108 safe circle
  $pair2 = New-Canvas $canvasPx
  $fg = $pair2[0]; $fgG = $pair2[1]
  $off = [int](($canvasPx - $contentPx) / 2)
  $dest = New-Object System.Drawing.Rectangle($off, $off, $contentPx, $contentPx)
  $fgG.DrawImage($src, $dest, $crop, [System.Drawing.GraphicsUnit]::Pixel)
  $fgG.Dispose()
  Save-Png $fg (Join-Path $dir 'ic_launcher_foreground.png')
  $fg.Dispose()

  Write-Host ("wrote mipmap-{0}: legacy {1}px, foreground {2}px (content {3}px)" -f $name, $legacyPx, $canvasPx, $contentPx)
}

$src.Dispose()
Write-Host 'done.'
