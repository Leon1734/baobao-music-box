Add-Type @'
using System;using System.Text;using System.Runtime.InteropServices;
public class WL{
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [StructLayout(LayoutKind.Sequential)] public struct RECT{public int L,T,R,B;}
}
'@
$rows = New-Object System.Collections.ArrayList
$cb = [WL+EnumProc]{
  param($h,$l)
  if([WL]::IsWindowVisible($h)){
    $r = New-Object WL+RECT
    [WL]::GetWindowRect($h, [ref]$r) | Out-Null
    $w = $r.R - $r.L; $ht = $r.B - $r.T
    if($w -gt 500 -and $ht -gt 400){
      $sb = New-Object System.Text.StringBuilder 300
      [WL]::GetWindowTextW($h, $sb, 300) | Out-Null
      $pp = 0
      [WL]::GetWindowThreadProcessId($h, [ref]$pp) | Out-Null
      $nm = ''
      try { $nm = (Get-Process -Id $pp -ErrorAction Stop).ProcessName } catch {}
      [void]$rows.Add([pscustomobject]@{PID=$pp;Proc=$nm;Size="${w}x${ht}";Title=$sb.ToString()})
    }
  }
  return $true
}
[WL]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
$rows | Sort-Object PID | Format-Table -AutoSize | Out-String -Width 200
