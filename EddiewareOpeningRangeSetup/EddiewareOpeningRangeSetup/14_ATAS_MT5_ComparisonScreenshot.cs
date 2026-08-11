using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace ATAS.Indicators
{
    internal static class AtasMt5ComparisonScreenshot
    {
        private const uint PwRenderFullContent = 0x00000002;

        public static string? Capture(
            string outputFolder,
            string status,
            string detail,
            string prices)
        {
            try
            {
                var atasHandle = FindAtasChartWindow();
                var mt5Handle = FindMt5ChartWindow();
                if (atasHandle == IntPtr.Zero || mt5Handle == IntPtr.Zero)
                    return null;

                using var atas = CaptureWindow(atasHandle);
                using var mt5 = CaptureWindow(mt5Handle);
                if (atas == null || mt5 == null)
                    return null;

                const int canvasWidth = 1800;
                const int canvasHeight = 880;
                const int headerHeight = 100;
                const int gap = 12;
                var panelWidth = (canvasWidth - gap * 3) / 2;
                var panelHeight = canvasHeight - headerHeight - gap * 2;

                using var canvas = new Bitmap(canvasWidth, canvasHeight, PixelFormat.Format24bppRgb);
                using var graphics = Graphics.FromImage(canvas);
                graphics.Clear(Color.FromArgb(18, 18, 20));
                graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
                graphics.SmoothingMode = SmoothingMode.HighQuality;
                graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;

                using var titleFont = new Font("Arial", 20, FontStyle.Bold);
                using var detailFont = new Font("Arial", 11, FontStyle.Regular);
                using var labelFont = new Font("Arial", 13, FontStyle.Bold);
                using var statusBrush = new SolidBrush(StatusColor(status));
                using var whiteBrush = new SolidBrush(Color.White);
                using var grayBrush = new SolidBrush(Color.Gainsboro);
                using var borderPen = new Pen(Color.FromArgb(80, 80, 86), 2);

                graphics.DrawString(status, titleFont, statusBrush, gap, 8);
                graphics.DrawString(detail, detailFont, whiteBrush, gap, 43);
                graphics.DrawString(prices, detailFont, grayBrush, gap, 67);

                var leftPanel = new Rectangle(gap, headerHeight + gap, panelWidth, panelHeight);
                var rightPanel = new Rectangle(gap * 2 + panelWidth, headerHeight + gap, panelWidth, panelHeight);
                DrawWindow(graphics, atas, leftPanel, "ATAS · NQ · DATA L2", labelFont, whiteBrush, borderPen);
                DrawWindow(graphics, mt5, rightPanel, "MT5 · USTEC · CFD", labelFont, whiteBrush, borderPen);

                var screenshotFolder = Path.Combine(outputFolder, "screenshots");
                Directory.CreateDirectory(screenshotFolder);
                var path = Path.Combine(
                    screenshotFolder,
                    $"atas_mt5_lead_{DateTime.UtcNow:yyyyMMdd_HHmmss_fff}.png");
                canvas.Save(path, ImageFormat.Png);
                return path;
            }
            catch
            {
                return null;
            }
        }

        private static void DrawWindow(
            Graphics graphics,
            Bitmap source,
            Rectangle panel,
            string label,
            Font labelFont,
            Brush labelBrush,
            Pen borderPen)
        {
            graphics.DrawRectangle(borderPen, panel);
            const int labelHeight = 30;
            graphics.DrawString(label, labelFont, labelBrush, panel.X + 8, panel.Y + 4);
            var imageArea = new Rectangle(
                panel.X + 3,
                panel.Y + labelHeight,
                panel.Width - 6,
                panel.Height - labelHeight - 3);
            var destination = Fit(source.Size, imageArea);
            graphics.DrawImage(source, destination);
        }

        private static Rectangle Fit(Size source, Rectangle bounds)
        {
            var ratio = Math.Min(
                (double)bounds.Width / Math.Max(1, source.Width),
                (double)bounds.Height / Math.Max(1, source.Height));
            var width = Math.Max(1, (int)Math.Round(source.Width * ratio));
            var height = Math.Max(1, (int)Math.Round(source.Height * ratio));
            return new Rectangle(
                bounds.X + (bounds.Width - width) / 2,
                bounds.Y + (bounds.Height - height) / 2,
                width,
                height);
        }

        private static Color StatusColor(string status)
        {
            if (status.Contains("ATAS", StringComparison.OrdinalIgnoreCase))
                return Color.DeepSkyBlue;
            if (status.Contains("CFD", StringComparison.OrdinalIgnoreCase) ||
                status.Contains("MT5", StringComparison.OrdinalIgnoreCase))
            {
                return Color.Violet;
            }
            return Color.LimeGreen;
        }

        private static Bitmap? CaptureWindow(IntPtr handle)
        {
            if (!GetWindowRect(handle, out var rect))
                return null;

            var width = rect.Right - rect.Left;
            var height = rect.Bottom - rect.Top;
            if (width < 100 || height < 100 || width > 10000 || height > 10000)
                return null;

            var bitmap = new Bitmap(width, height, PixelFormat.Format24bppRgb);
            using var graphics = Graphics.FromImage(bitmap);
            var deviceContext = graphics.GetHdc();
            try
            {
                if (!PrintWindow(handle, deviceContext, PwRenderFullContent))
                {
                    graphics.ReleaseHdc(deviceContext);
                    deviceContext = IntPtr.Zero;
                    graphics.CopyFromScreen(rect.Left, rect.Top, 0, 0, new Size(width, height));
                }
            }
            finally
            {
                if (deviceContext != IntPtr.Zero)
                    graphics.ReleaseHdc(deviceContext);
            }

            return bitmap;
        }

        private static IntPtr FindAtasChartWindow()
        {
            var process = Process.GetCurrentProcess();
            var candidates = FindTopLevelWindows(process.Id);
            var best = FindLargestMatching(candidates, title =>
                title.Contains("NQ", StringComparison.OrdinalIgnoreCase) &&
                (title.Contains("Chart", StringComparison.OrdinalIgnoreCase) ||
                 title.Contains("1m", StringComparison.OrdinalIgnoreCase)));
            if (best != IntPtr.Zero)
                return best;

            var childCandidates = FindChildWindows(process.MainWindowHandle);
            best = FindLargestMatching(childCandidates, title =>
                title.Contains("NQ", StringComparison.OrdinalIgnoreCase));
            return best != IntPtr.Zero ? best : process.MainWindowHandle;
        }

        private static IntPtr FindMt5ChartWindow()
        {
            foreach (var process in Process.GetProcessesByName("terminal64"))
            {
                try
                {
                    var children = FindChildWindows(process.MainWindowHandle);
                    var match = FindLargestMatching(children, title =>
                        title.Contains("USTEC", StringComparison.OrdinalIgnoreCase) &&
                        title.Contains("M1", StringComparison.OrdinalIgnoreCase));
                    if (match != IntPtr.Zero)
                        return match;
                }
                catch
                {
                    // Continue with the next terminal instance.
                }
                finally
                {
                    process.Dispose();
                }
            }

            return IntPtr.Zero;
        }

        private static IntPtr FindLargestMatching(
            IEnumerable<WindowCandidate> candidates,
            Func<string, bool> titleMatch)
        {
            var best = IntPtr.Zero;
            long bestArea = 0;
            foreach (var candidate in candidates)
            {
                if (!titleMatch(candidate.Title))
                    continue;
                var area = (long)Math.Max(0, candidate.Rect.Right - candidate.Rect.Left) *
                           Math.Max(0, candidate.Rect.Bottom - candidate.Rect.Top);
                if (area > bestArea)
                {
                    bestArea = area;
                    best = candidate.Handle;
                }
            }
            return best;
        }

        private static List<WindowCandidate> FindTopLevelWindows(int processId)
        {
            var results = new List<WindowCandidate>();
            EnumWindows((handle, _) =>
            {
                GetWindowThreadProcessId(handle, out var ownerProcessId);
                if (ownerProcessId == processId && IsWindowVisible(handle))
                    AddCandidate(results, handle);
                return true;
            }, IntPtr.Zero);
            return results;
        }

        private static List<WindowCandidate> FindChildWindows(IntPtr parent)
        {
            var results = new List<WindowCandidate>();
            if (parent == IntPtr.Zero)
                return results;

            EnumChildWindows(parent, (handle, _) =>
            {
                AddCandidate(results, handle);
                return true;
            }, IntPtr.Zero);
            return results;
        }

        private static void AddCandidate(List<WindowCandidate> results, IntPtr handle)
        {
            var length = GetWindowTextLength(handle);
            if (length <= 0 || !GetWindowRect(handle, out var rect))
                return;
            var text = new StringBuilder(length + 1);
            GetWindowText(handle, text, text.Capacity);
            results.Add(new WindowCandidate(handle, text.ToString(), rect));
        }

        private readonly record struct WindowCandidate(IntPtr Handle, string Title, NativeRect Rect);

        private delegate bool EnumWindowsCallback(IntPtr handle, IntPtr parameter);

        [StructLayout(LayoutKind.Sequential)]
        private struct NativeRect
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsCallback callback, IntPtr parameter);

        [DllImport("user32.dll")]
        private static extern bool EnumChildWindows(IntPtr parent, EnumWindowsCallback callback, IntPtr parameter);

        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr handle);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr handle, out int processId);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowTextLength(IntPtr handle);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr handle, StringBuilder text, int maximumCount);

        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr handle, out NativeRect rect);

        [DllImport("user32.dll")]
        private static extern bool PrintWindow(IntPtr handle, IntPtr deviceContext, uint flags);
    }
}
