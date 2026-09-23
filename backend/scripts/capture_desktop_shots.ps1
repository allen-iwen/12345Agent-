# 截取桌面上的 AI 工具窗口，作为「在桌面上使用 AI 工具」的证据。
#
# 关键技术点（都是踩坑后定下来的）：
#   1. 用 PrintWindow 让目标窗口渲染自身，只得到该窗口的内容，
#      压在它上方的置顶窗口不会被一起拍进去（屏幕区域截图做不到这一点）。
#   2. 被遮挡的 Chromium 窗口会暂停渲染，PrintWindow 拿到的是旧帧。
#      加 -Live 时先用 SWP_NOACTIVATE 把窗口提到最前——它可见后才会重绘，
#      而 NOACTIVATE 保证不夺走使用者当前窗口的键盘焦点。
#   3. 同名窗口可能有多个（主窗 + 提示窗），取面积最大的那个。
#   4. 文件名含中文时 GDI+ 保存会报「一般性错误」，因此先写 ASCII 临时路径再复制。
#   5. 最小化窗口的矩形是 160x28，据此识别并跳过。
#
# 用法：
#   powershell -File scripts\capture_desktop_shots.ps1
#   powershell -File scripts\capture_desktop_shots.ps1 -Live
#   powershell -File scripts\capture_desktop_shots.ps1 -Patterns "DeepSeek Harness","Visual Studio Code"
param(
    [string[]]$Patterns = @("DeepSeek Harness"),
    [string]$OutDir = "D:\workspace\12345工单热线\12345agent\docs\competition\shots",
    [switch]$Live,
    [int]$MinWidth = 1200
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Drawing;

public class WinShot {
    public delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }

    // 取面积最大的同名可见窗口，避免命中提示窗等小窗口
    public static IntPtr FindBiggest(string needle, out string report) {
        IntPtr best = IntPtr.Zero; int bestArea = 0; var found = new List<string>();
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            if (!IsWindowVisible(h)) return true;
            var sb = new StringBuilder(400); GetWindowText(h, sb, 400);
            string t = sb.ToString();
            if (t.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0) {
                RECT r; GetWindowRect(h, out r);
                int w = r.R - r.L, ht = r.B - r.T;
                found.Add(t + " [" + w + "x" + ht + "]");
                if (w * ht > bestArea) { bestArea = w * ht; best = h; }
            }
            return true;
        }, IntPtr.Zero);
        report = found.Count == 0 ? "(无匹配)" : string.Join(" | ", found.ToArray());
        return best;
    }

    // 提到最前但不激活：窗口可见后会恢复渲染，同时不抢键盘焦点
    public static void RaiseNoActivate(IntPtr h) {
        SetWindowPos(h, (IntPtr)(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010);
    }

    public static string ShotSelf(IntPtr h, string path) {
        RECT r; GetWindowRect(h, out r);
        int w = r.R - r.L, ht = r.B - r.T;
        if (w <= 0 || ht <= 0) return "0x0";
        using (var bmp = new Bitmap(w, ht))
        using (var g = Graphics.FromImage(bmp)) {
            IntPtr hdc = g.GetHdc();
            PrintWindow(h, hdc, 2);          // PW_RENDERFULLCONTENT
            g.ReleaseHdc(hdc);
            bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
        }
        return w + "x" + ht;
    }
}
"@

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$tmpRoot = Join-Path $env:TEMP ("winshot_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null

$index = 0
$exitCode = 0
foreach ($pat in $Patterns) {
    $report = ""
    $h = [WinShot]::FindBiggest($pat, [ref]$report)
    Write-Output "  匹配窗口：$report"
    if ($h -eq [IntPtr]::Zero) { Write-Output "  [MISS] 未找到窗口：$pat"; $exitCode = 1; continue }

    if ($Live) {
        [WinShot]::RaiseNoActivate($h)
        Start-Sleep -Milliseconds 2500      # 等 Chromium 重绘
    }

    $index++
    $safe = ($pat -replace '[^A-Za-z0-9]', '')
    $name = "desktop_$('{0:d2}' -f $index)_$safe.png"
    $tmpFile = Join-Path $tmpRoot "$index.png"

    $size = [WinShot]::ShotSelf($h, $tmpFile)
    $img = [System.Drawing.Image]::FromFile($tmpFile)
    $w = $img.Width; $img.Dispose()

    if ($w -lt $MinWidth) {
        Write-Output "  [SKIP] $pat 尺寸 $size 小于 $MinWidth（窗口可能已最小化，请先恢复窗口）"
        Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
        $exitCode = 1
        continue
    }
    Copy-Item $tmpFile (Join-Path $OutDir $name) -Force
    $hash = (Get-FileHash (Join-Path $OutDir $name)).Hash.Substring(0, 12)
    Write-Output ("  [OK  ] {0}  ->  {1}  ({2}, hash={3})" -f $pat, $name, $size, $hash)
}

Remove-Item $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "输出目录：$OutDir"
Write-Output "说明：只抓取匹配到的窗口自身；-Live 会把它提到最前以恢复渲染，但不抢键盘焦点。"
exit $exitCode
