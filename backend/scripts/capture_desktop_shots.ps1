# 截取桌面上的 AI 工具窗口，作为「在桌面上使用 AI 工具」的补充证据。
#
# 用 Win32 PrintWindow + PW_RENDERFULLCONTENT 直接让目标窗口渲染自身，
# 不需要把窗口切到前台，避免打断使用者、也不会把无关窗口拍进去。
# 若某个窗口拒绝离屏渲染（图片全黑/纯白），自动退回「置前 + 屏幕区域抓取」。
#
# 用法：
#   pwsh -File scripts/capture_desktop_shots.ps1
#   pwsh -File scripts/capture_desktop_shots.ps1 -Patterns "DeepSeek Harness","PowerShell"
param(
    [string[]]$Patterns = @("DeepSeek Harness", "PowerShell", "Visual Studio Code"),
    [string]$OutDir = "D:\workspace\12345工单热线\12345agent\docs\competition\shots",
    [switch]$AllowForeground
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Drawing;

public class WinCap {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }

    public static List<IntPtr> Find(string needle) {
        var found = new List<IntPtr>();
        EnumWindows(delegate(IntPtr h, IntPtr p) {
            if (!IsWindowVisible(h)) return true;
            var sb = new StringBuilder(400);
            GetWindowText(h, sb, 400);
            string t = sb.ToString();
            if (t.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0) found.Add(h);
            return true;
        }, IntPtr.Zero);
        return found;
    }

    // 抓取窗口：先离屏渲染，失败则由调用方决定是否置前
    public static string Grab(IntPtr h, string path, bool foreground) {
        RECT r; GetWindowRect(h, out r);
        int w = r.R - r.L, ht = r.B - r.T;
        if (w <= 0 || ht <= 0) return "empty-rect";
        if (foreground) {
            ShowWindow(h, 9);           // SW_RESTORE
            SetForegroundWindow(h);
            System.Threading.Thread.Sleep(700);
        }
        using (var bmp = new Bitmap(w, ht))
        using (var g = Graphics.FromImage(bmp)) {
            bool ok = false;
            if (!foreground) {
                IntPtr hdc = g.GetHdc();
                ok = PrintWindow(h, hdc, 2);   // PW_RENDERFULLCONTENT
                g.ReleaseHdc(hdc);
            }
            if (!ok) {
                g.CopyFromScreen(r.L, r.T, 0, 0, new Size(w, ht));
            }
            bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
        }
        return "ok";
    }

    // 判定是否拍到真实内容：统计采样点的颜色种类与亮度跨度
    public static string Judge(string path) {
        using (var bmp = new Bitmap(path)) {
            var colors = new HashSet<int>();
            int min = 255, max = 0;
            for (int y = 0; y < bmp.Height; y += Math.Max(1, bmp.Height / 60))
            for (int x = 0; x < bmp.Width; x += Math.Max(1, bmp.Width / 60)) {
                Color c = bmp.GetPixel(x, y);
                colors.Add(c.ToArgb());
                int lum = (c.R + c.G + c.B) / 3;
                if (lum < min) min = lum;
                if (lum > max) max = lum;
            }
            return string.Format("colors={0} lumRange={1}", colors.Count, max - min);
        }
    }
}
"@

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$index = 0
foreach ($pat in $Patterns) {
    $handles = [WinCap]::Find($pat)
    if ($handles.Count -eq 0) { Write-Output "  [MISS] 未找到窗口：$pat"; continue }
    $h = $handles[0]
    $index++
    $safe = ($pat -replace '[^A-Za-z0-9]', '')
    $name = "desktop_$('{0:d2}' -f $index)_$safe.png"
    $path = Join-Path $OutDir $name

    $rc = [WinCap]::Grab($h, $path, $false)
    $judge = [WinCap]::Judge($path)
    # 离屏渲染常对部分窗口返回空白，此时才考虑置前抓取
    if ($AllowForeground -and ($judge -match "colors=(\d+)" -and [int]$Matches[1] -lt 12)) {
        Write-Output "  [retry] $pat 离屏渲染结果偏空白，改用置前抓取"
        $rc = [WinCap]::Grab($h, $path, $true)
        $judge = [WinCap]::Judge($path)
    }
    $kb = [int]((Get-Item $path).Length / 1024)
    Write-Output ("  [OK  ] {0}  ->  {1}  ({2} KB, {3})" -f $pat, $name, $kb, $judge)
}

Write-Output "输出目录：$OutDir"
Write-Output "提示：本脚本只抓取匹配到的窗口本身，不会把整个桌面（含聊天工具等无关内容）拍进去。"
