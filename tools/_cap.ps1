Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type @'
using System;using System.Text;using System.Runtime.InteropServices;
public class WE{
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [StructLayout(LayoutKind.Sequential)] public struct RECT{public int L,T,R,B;}
}
'@
$target = [uint32]$args[0]
$found = @()
$cb = [WE+EnumProc]{
  param($h,$l)
  $pid2 = 0
  [WE]::GetWindowThreadProcessId($h, [ref]$pid2) | Out-Null
  if($pid2 -eq $target -and [WE]::IsWindowVisible($h)){
    $r = New-Object WE+RECT
    [WE]::GetWindowRect($h, [ref]$r) | Out-Null
    $w = $r.R - $r.L; $ht = $r.B - $r.T
    if($w -gt 300 -and $ht -gt 300){ $script:found += ,@($h,$w,$ht) }
  }
  return $true
}
[WE]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
Write-Host "找到 $($found.Count) 个可见大窗口"
if($found.Count -gt 0){
  $f = $found[0]
  [WE]::ShowWindow($f[0], 9) | Out-Null
  [WE]::SetForegroundWindow($f[0]) | Out-Null
  Start-Sleep -Milliseconds 1500
  $r = New-Object WE+RECT
  [WE]::GetWindowRect($f[0], [ref]$r) | Out-Null
  $w = $r.R - $r.L; $ht = $r.B - $r.T
  Write-Host "窗口 ${w}x${ht} @ $($r.L),$($r.T)"
  $bmp = New-Object System.Drawing.Bitmap $w, $ht
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $w, $ht))
  $bmp.Save('E:\Workspace_AI\Hermes\Music\_app.png', [System.Drawing.Imaging.ImageFormat]::Png)
  Write-Host "saved _app.png"
}
